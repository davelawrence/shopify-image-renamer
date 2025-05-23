import os
import requests
import time
import csv
from dotenv import load_dotenv
from functools import wraps

print("Starting script...")
load_dotenv()

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
API_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN")
PRODUCT_ID = "gid://shopify/Product/9678733148457"

print(f"SHOPIFY_STORE: {SHOPIFY_STORE}")
print(f"API_TOKEN exists: {bool(API_TOKEN)}")
print(f"PRODUCT_ID: {PRODUCT_ID}")

HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": API_TOKEN
}

API_URL = f"https://{SHOPIFY_STORE}/admin/api/2023-10/graphql.json"

# Retry decorator for API calls
def retry_on_rate_limit(max_retries=5, backoff_factor=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            delay = 1
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if hasattr(e, 'response') and e.response is not None and e.response.status_code == 429:
                        if retries < max_retries:
                            print(f"Rate limit hit. Retrying in {delay} seconds...")
                            time.sleep(delay)
                            retries += 1
                            delay *= backoff_factor
                        else:
                            print("Max retries reached. Aborting.")
                            raise
                    else:
                        raise
        return wrapper
    return decorator

@retry_on_rate_limit()
def graphql(query, variables=None):
    response = requests.post(API_URL, json={"query": query, "variables": variables}, headers=HEADERS)
    if response.status_code != 200:
        raise Exception(f"GraphQL Error: {response.text}")
    return response.json()

def clean(text):
    # Remove pipes, extra dashes, and clean up the text
    cleaned = text.lower().replace("|", " ").replace("/", "-").replace(",", "").replace("&", "and")
    cleaned = cleaned.replace(" ", "-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-")
    return cleaned

def get_product_data():
    query = """
    query getProduct($id: ID!) {
      product(id: $id) {
        id
        handle
        title
        images(first: 100) {
          edges {
            node {
              id
              originalSrc
              altText
            }
          }
        }
        variants(first: 100) {
          edges {
            node {
              id
              title
              selectedOptions {
                name
                value
              }
              image {
                id
              }
            }
          }
        }
      }
    }
    """
    variables = {"id": PRODUCT_ID}
    data = graphql(query, variables)
    if 'data' not in data:
        print('API response:', data)
        raise Exception("Shopify API response does not contain 'data'. Check your credentials, permissions, and product ID.")
    return data['data']['product']

def download_image(url, filename):
    r = requests.get(url)
    with open(filename, 'wb') as f:
        f.write(r.content)

def upload_image_to_shopify_files(filename):
    # Step 1: Get a staged upload URL
    staged_upload_query = """
    mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
      stagedUploadsCreate(input: $input) {
        stagedTargets {
          url
          resourceUrl
          parameters {
            name
            value
          }
        }
      }
    }
    """
    staged_upload_variables = {
        "input": [
            {
                "resource": "FILE",
                "filename": filename,
                "mimeType": "image/jpeg",
                "httpMethod": "POST"
            }
        ]
    }
    staged_upload_response = graphql(staged_upload_query, staged_upload_variables)
    if 'data' not in staged_upload_response or 'stagedUploadsCreate' not in staged_upload_response['data']:
        print("Full staged_upload_response:", staged_upload_response)
        raise Exception("Failed to get staged upload URL")
    staged_target = staged_upload_response['data']['stagedUploadsCreate']['stagedTargets'][0]
    upload_url = staged_target['url']
    parameters = {param['name']: param['value'] for param in staged_target['parameters']}
    with open(filename, 'rb') as f:
        files = {'file': f}
        upload_response = requests.post(upload_url, data=parameters, files=files)
        if upload_response.status_code not in (200, 201):
            raise Exception(f"Failed to upload file: {upload_response.text}")
    # Step 2: Register the file in Shopify Files
    files_create_query = """
    mutation filesCreate($files: [FileCreateInput!]!) {
      filesCreate(files: $files) {
        files {
          url
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    files_create_variables = {
        "files": [
            {
                "originalSource": staged_target['resourceUrl'],
                "contentType": "IMAGE",
                "alt": filename
            }
        ]
    }
    files_create_response = graphql(files_create_query, files_create_variables)
    if 'data' not in files_create_response or 'filesCreate' not in files_create_response['data']:
        print("Full files_create_response:", files_create_response)
        raise Exception("Failed to create file in Shopify Files")
    file_url = files_create_response['data']['filesCreate']['files'][0]['url']
    return file_url

def main():
    product = get_product_data()
    title = clean(product['title'])
    handle = product['handle']
    product_id = product['id'].split('/')[-1] if '/' in product['id'] else product['id']
    # Get actual option names from the product (preserve case and spaces)
    option_names = [opt['name'] for opt in product.get('variants', {}).get('edges', [{}])[0].get('node', {}).get('selectedOptions', [])]
    while len(option_names) < 3:
        option_names.append(f'Option{len(option_names)+1}')
    # Build variant mapping
    image_to_variant = {}
    variant_id_to_options = {}
    for variant in product['variants']['edges']:
        variant_node = variant['node']
        variant_id = variant_node['id'].split('/')[-1] if '/' in variant_node['id'] else variant_node['id']
        options = [opt['value'] for opt in variant_node['selectedOptions']]
        while len(options) < 3:
            options.append('')
        variant_id_to_options[variant_id] = options
        if variant_node['image']:
            image_id = variant_node['image']['id']
            image_to_variant[image_id] = (variant_id, options)
    current_variant_key = None
    variant_image_counts = {}
    variant_first_image_written = {}
    original_images = product['images']['edges'] if 'images' in product else []
    csv_rows = []
    for idx, img in enumerate(original_images):
        node = img['node']
        original_url = node['originalSrc']
        variant_options = ['', '', '']
        variant_id = ''
        if node['id'] in image_to_variant:
            variant_id, variant_options = image_to_variant[node['id']]
            current_variant_key = "-".join(variant_options)
        if node['id'] not in image_to_variant and current_variant_key:
            variant_options = current_variant_key.split("-")
        variant_key = "-".join([clean(opt) for opt in variant_options])
        if variant_key not in variant_image_counts:
            variant_image_counts[variant_key] = 1
        else:
            variant_image_counts[variant_key] += 1
        suffix = str(variant_image_counts[variant_key]).zfill(2)
        new_filename = f"{title}-{variant_key}-{suffix}.jpg"
        print(f"Processing image: {new_filename}")
        print(f"  Variant options: {variant_options}")
        download_image(original_url, new_filename)
        print(f"Downloaded and renamed: {new_filename}")
        file_url = upload_image_to_shopify_files(new_filename)
        print(f"Uploaded to Shopify Files: {file_url}")
        image_command = 'REPLACE' if idx == 0 else 'MERGE'
        # Only set Variant Image for the first image of each variant
        variant_image_url = ''
        if variant_id:
            if variant_id not in variant_first_image_written:
                variant_image_url = file_url
                variant_first_image_written[variant_id] = True
        row = {
            'ID': product_id,
            'Handle': handle,
            'Image Type': 'IMAGE',
            'Image Src': file_url,
            'Image Command': image_command,
            'Image Position': idx + 1,
            'Variant ID': variant_id,
            'Option1 Name': option_names[0],
            'Option1 Value': variant_options[0],
            'Option2 Name': option_names[1],
            'Option2 Value': variant_options[1],
            'Option3 Name': option_names[2],
            'Option3 Value': variant_options[2],
            'Variant Image': variant_image_url
        }
        csv_rows.append(row)
        time.sleep(1)
    # Write CSV
    csv_filename = 'matrixify-import.csv'
    fieldnames = ['ID','Handle','Image Type','Image Src','Image Command','Image Position','Variant ID','Option1 Name','Option1 Value','Option2 Name','Option2 Value','Option3 Name','Option3 Value','Variant Image']
    with open(csv_filename, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in csv_rows:
            writer.writerow(row)
    print(f"Wrote Matrixify CSV: {csv_filename}")

if __name__ == "__main__":
    main()
