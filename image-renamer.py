import os
import requests
import time
import csv
import json
import argparse
from dotenv import load_dotenv
from functools import wraps

print("Starting script...")
load_dotenv()

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
API_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN")
PRODUCT_ID = os.getenv("PRODUCT_ID", "gid://shopify/Product/9678733148457")

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

# --- Pipeline Stages ---

def download_images(product, output_dir="downloaded_images"):
    os.makedirs(output_dir, exist_ok=True)
    images = product['images']['edges'] if 'images' in product else []
    manifest = []
    for img in images:
        node = img['node']
        url = node['originalSrc']
        image_id = node['id']
        filename = os.path.join(output_dir, f"{image_id}.jpg")
        download_image(url, filename)
        manifest.append({'image_id': image_id, 'original_url': url, 'filename': filename})
    with open('download_manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"Downloaded {len(manifest)} images. Manifest saved to download_manifest.json.")
    return manifest

def rename_images(product, manifest, output_dir="renamed_images"):
    os.makedirs(output_dir, exist_ok=True)
    # Dynamically get all option names from all variants
    all_option_names = set()
    for variant in product['variants']['edges']:
        for opt in variant['node']['selectedOptions']:
            all_option_names.add(opt['name'])
    option_names = list(all_option_names)
    option_names.sort()
    # Build mapping: image_id -> list of (variant_id, options)
    image_to_variants = {}
    for variant in product['variants']['edges']:
        variant_node = variant['node']
        variant_id = variant_node['id'].split('/')[-1] if '/' in variant_node['id'] else variant_node['id']
        options = [opt['value'] for opt in variant_node['selectedOptions']]
        while len(options) < len(option_names):
            options.append('')
        if variant_node['image']:
            image_id = variant_node['image']['id']
            if image_id not in image_to_variants:
                image_to_variants[image_id] = []
            image_to_variants[image_id].append((variant_id, options))
    renamed_manifest = []
    gallery_position = 1
    for entry in manifest:
        image_id = entry['image_id']
        original_file = entry['filename']
        if image_id in image_to_variants:
            for idx, (variant_id, options) in enumerate(image_to_variants[image_id]):
                variant_key = "-".join([clean(opt) for opt in options])
                suffix = str(idx+1).zfill(2) if len(image_to_variants[image_id]) > 1 else "01"
                new_filename = f"{clean(product['title'])}-{variant_key}-{suffix}.jpg"
                new_path = os.path.join(output_dir, new_filename)
                with open(original_file, 'rb') as src, open(new_path, 'wb') as dst:
                    dst.write(src.read())
                renamed_manifest.append({
                    'variant_id': variant_id,
                    'options': options,
                    'filename': new_path,
                    'gallery_position': gallery_position
                })
                gallery_position += 1
        else:
            new_filename = f"{clean(product['title'])}-gallery-{gallery_position:02d}.jpg"
            new_path = os.path.join(output_dir, new_filename)
            with open(original_file, 'rb') as src, open(new_path, 'wb') as dst:
                dst.write(src.read())
            renamed_manifest.append({
                'variant_id': '',
                'options': [],
                'filename': new_path,
                'gallery_position': gallery_position
            })
            gallery_position += 1
    with open('renamed_manifest.json', 'w') as f:
        json.dump(renamed_manifest, f, indent=2)
    print(f"Renamed images. Manifest saved to renamed_manifest.json.")
    return renamed_manifest, option_names

def upload_images(renamed_manifest):
    upload_manifest = []
    for entry in renamed_manifest:
        file_url = upload_image_to_shopify_files(entry['filename'])
        upload_manifest.append({
            **entry,
            'file_url': file_url
        })
        time.sleep(1)
    with open('upload_manifest.json', 'w') as f:
        json.dump(upload_manifest, f, indent=2)
    print(f"Uploaded images. Manifest saved to upload_manifest.json.")
    return upload_manifest

def generate_matrixify_csv(product, upload_manifest, option_names):
    product_id = product['id'].split('/')[-1] if '/' in product['id'] else product['id']
    handle = product['handle']
    csv_rows = []
    for entry in upload_manifest:
        row = {
            'ID': product_id,
            'Handle': handle,
            'Image Type': 'IMAGE',
            'Image Src': entry['file_url'],
            'Image Command': 'REPLACE' if entry['gallery_position'] == 1 else 'MERGE',
            'Image Position': entry['gallery_position'],
            'Variant ID': entry['variant_id'],
        }
        for i, name in enumerate(option_names):
            row[f'Option{i+1} Name'] = name
            row[f'Option{i+1} Value'] = entry['options'][i] if i < len(entry['options']) else ''
        row['Variant Image'] = entry['file_url'] if entry['variant_id'] else ''
        csv_rows.append(row)
    # Build fieldnames dynamically
    max_options = len(option_names)
    fieldnames = ['ID','Handle','Image Type','Image Src','Image Command','Image Position','Variant ID']
    for i in range(max_options):
        fieldnames.append(f'Option{i+1} Name')
        fieldnames.append(f'Option{i+1} Value')
    fieldnames.append('Variant Image')
    csv_filename = 'matrixify-import.csv'
    with open(csv_filename, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in csv_rows:
            writer.writerow(row)
    print(f"Wrote Matrixify CSV: {csv_filename}")

# --- CLI Controller ---
def confirm_step(message):
    input(f"\n{message}\nPress Enter to continue...")

def main():
    parser = argparse.ArgumentParser(description="Shopify Image Renamer Pipeline")
    parser.add_argument('--stage', choices=['download', 'rename', 'upload', 'generate-csv', 'all'], default='all', help='Pipeline stage to run')
    parser.add_argument('--confirm', action='store_true', help='Pause for confirmation after each stage')
    args = parser.parse_args()

    product = get_product_data()
    manifests = {}
    option_names = []

    if args.stage in ['download', 'all']:
        manifests['download'] = download_images(product)
        if args.confirm:
            confirm_step("Download stage complete. Verify downloaded images and manifest.")
    if args.stage in ['rename', 'all']:
        if 'download' not in manifests:
            with open('download_manifest.json') as f:
                manifests['download'] = json.load(f)
        manifests['rename'], option_names = rename_images(product, manifests['download'])
        if args.confirm:
            confirm_step("Rename stage complete. Verify renamed images and manifest.")
    if args.stage in ['upload', 'all']:
        if 'rename' not in manifests:
            with open('renamed_manifest.json') as f:
                manifests['rename'] = json.load(f)
            # Option names are needed for CSV
            all_option_names = set()
            for variant in product['variants']['edges']:
                for opt in variant['node']['selectedOptions']:
                    all_option_names.add(opt['name'])
            option_names = list(all_option_names)
            option_names.sort()
        manifests['upload'] = upload_images(manifests['rename'])
        if args.confirm:
            confirm_step("Upload stage complete. Verify uploaded image URLs and manifest.")
    if args.stage in ['generate-csv', 'all']:
        if 'upload' not in manifests:
            with open('upload_manifest.json') as f:
                manifests['upload'] = json.load(f)
            if not option_names:
                all_option_names = set()
                for variant in product['variants']['edges']:
                    for opt in variant['node']['selectedOptions']:
                        all_option_names.add(opt['name'])
                option_names = list(all_option_names)
                option_names.sort()
        generate_matrixify_csv(product, manifests['upload'], option_names)
        if args.confirm:
            confirm_step("CSV generation complete. Verify matrixify-import.csv.")

if __name__ == "__main__":
    main()
