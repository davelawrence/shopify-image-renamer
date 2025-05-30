import os
import requests
import time
import csv
import json
import argparse
from dotenv import load_dotenv
from functools import wraps
from datetime import datetime, timezone, timedelta
import boto3
import mimetypes
import sys

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
API_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN")

if not SHOPIFY_STORE or not API_TOKEN:
    print("Error: Required environment variables SHOPIFY_STORE and SHOPIFY_ADMIN_API_TOKEN must be set")
    sys.exit(1)

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
    cleaned = text.lower().replace("|", " ").replace("/", "-").replace(",", "").replace("&", "and").replace("+", "-")
    cleaned = cleaned.replace(" ", "-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-")
    return cleaned

def get_product_data(product_id):
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
    variables = {"id": product_id}
    data = graphql(query, variables)
    print("\nAPI Response:", json.dumps(data, indent=2))
    if 'data' not in data:
        print('API response:', data)
        raise Exception("Shopify API response does not contain 'data'. Check your credentials, permissions, and product ID.")
    return data['data']['product']

def download_image(url, filename):
    r = requests.get(url)
    with open(filename, 'wb') as f:
        f.write(r.content)

def get_file_url_by_id(file_id, max_attempts=20, delay=2):
    query = """
    query getFile($id: ID!) {
      file(id: $id) {
        ... on MediaImage {
          id
          fileStatus
          preview {
            image {
              url
            }
          }
        }
      }
    }
    """
    variables = {"id": file_id}
    print("Waiting 10 seconds before polling for file status...")
    time.sleep(10)
    for attempt in range(max_attempts):
        response = graphql(query, variables)
        file_obj = response.get('data', {}).get('file')
        if file_obj:
            status = file_obj.get('fileStatus')
            url = None
            if file_obj.get('preview') and file_obj['preview'].get('image'):
                url = file_obj['preview']['image'].get('url')
            if status == 'READY' and url:
                return url
            print(f"Waiting for file to be READY (current status: {status}). Attempt {attempt+1}/{max_attempts}...")
        else:
            print(f"File with id {file_id} not found. Attempt {attempt+1}/{max_attempts}...")
        time.sleep(delay)
    raise Exception(f"File {file_id} did not become READY in time.")

def fetch_recent_file_url_by_filename(filename, max_files=50, minutes_window=10):
    # Query the most recent files from Shopify Files and try to match by filename and createdAt
    query = f"""
    query filesQuery {{
      files(first: {max_files}, sortKey: CREATED_AT, reverse: true) {{
        edges {{
          node {{
            ... on MediaImage {{
              id
              createdAt
              originalFile {{
                fileName
              }}
              preview {{
                image {{
                  url
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    response = graphql(query)
    files = response.get('data', {}).get('files', {}).get('edges', [])
    base_filename = filename.rsplit('.', 1)[0]  # Remove extension for matching
    now = datetime.now(timezone.utc)
    for edge in files:
        node = edge['node']
        file_name = node.get('originalFile', {}).get('fileName', '')
        created_at_str = node.get('createdAt')
        created_at = None
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            except Exception:
                pass
        # Fuzzy match: filename contains base_filename and created within the last X minutes
        if base_filename in file_name and created_at and (now - created_at) <= timedelta(minutes=minutes_window):
            url = node.get('preview', {}).get('image', {}).get('url')
            if url:
                print(f"Fallback: Found file by fuzzy match: {file_name} (created {created_at})")
                return url
    print(f"Fallback: No fuzzy match found for filename: {filename} in the last {minutes_window} minutes")
    return None

def upload_to_s3(file_path, s3_key):
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    bucket = os.getenv('AWS_S3_BUCKET')
    region = os.getenv('AWS_S3_REGION')
    
    if not all([aws_access_key_id, aws_secret_access_key, bucket, region]):
        raise ValueError("Missing required AWS environment variables")
        
    s3 = boto3.client(
        's3',
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region
    )
    content_type, _ = mimetypes.guess_type(file_path)
    extra_args = {'ContentType': content_type} if content_type else {}
    s3.upload_file(file_path, bucket, s3_key, ExtraArgs=extra_args)
    url = f'https://{bucket}.s3.{region}.amazonaws.com/{s3_key}'
    return url

def upload_images(renamed_manifest):
    upload_manifest = []
    # Handle both list and dict formats of renamed_manifest
    manifest_entries = renamed_manifest[0] if isinstance(renamed_manifest, tuple) else renamed_manifest
    for entry in manifest_entries:
        file_path = entry['filename']
        s3_key = os.path.basename(file_path)
        file_url = upload_to_s3(file_path, s3_key)
        upload_manifest.append({
            **entry,
            'file_url': file_url
        })
        time.sleep(1)
    with open('upload_manifest.json', 'w') as f:
        json.dump(upload_manifest, f, indent=2)
    print(f"Uploaded images to S3. Manifest saved to upload_manifest.json.")
    return upload_manifest

def generate_matrixify_csv(product, upload_manifest, option_names):
    product_id = product['id'].split('/')[-1] if '/' in product['id'] else product['id']
    handle = product['handle']
    title = clean(product['title'])
    # Build a mapping from variant_id to its images (in order)
    variant_to_images = {}
    product_level_images = []
    for entry in upload_manifest:
        if entry['variant_id']:
            variant_to_images.setdefault(entry['variant_id'], []).append(entry)
        else:
            product_level_images.append(entry)
    # Build the global gallery order
    gallery_list = []
    # Get all variant IDs in the order they appear in the product
    variant_ids = [v['node']['id'] for v in product['variants']['edges']]
    for variant_id in variant_ids:
        images = variant_to_images.get(variant_id, [])
        if images:
            # First image is mapped to the variant, rest are product-level
            for i, entry in enumerate(images):
                gallery_list.append({
                    **entry,
                    'variant_id': variant_id if i == 0 else None  # Only first image mapped to variant
                })
    # Add any remaining product-level images (not already included)
    used_image_ids = set(e['image_id'] for e in gallery_list)
    for entry in product_level_images:
        if entry['image_id'] not in used_image_ids:
            gallery_list.append(entry)
    # Assign global Image Position
    csv_rows = []
    for idx, entry in enumerate(gallery_list, 1):
        row = {
            'ID': product_id,
            'Handle': handle,
            'Image Type': 'IMAGE',
            'Image Src': entry['file_url'],
            'Image Command': 'REPLACE' if idx == 1 else 'MERGE',
            'Image Position': idx,
            'Variant ID': entry['variant_id'].split('/')[-1] if entry.get('variant_id') else '',
        }
        for i, name in enumerate(option_names):
            row[f'Option{i+1} Name'] = name
            row[f'Option{i+1} Value'] = entry['options'][i] if i < len(entry['options']) else ''
        row['Variant Image'] = entry['file_url'] if entry.get('variant_id') else ''
        csv_rows.append(row)
    # Build fieldnames dynamically
    max_options = len(option_names)
    fieldnames = ['ID','Handle','Image Type','Image Src','Image Command','Image Position','Variant ID']
    for i in range(max_options):
        fieldnames.append(f'Option{i+1} Name')
        fieldnames.append(f'Option{i+1} Value')
    fieldnames.append('Variant Image')
    csv_filename = f'matrixify-import-{title}.csv'
    with open(csv_filename, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in csv_rows:
            writer.writerow(row)
    print(f"Wrote Matrixify CSV: {csv_filename}")

def download_images(product, output_dir="downloaded_images"):
    os.makedirs(output_dir, exist_ok=True)
    images = product['images']['edges'] if 'images' in product else []
    # Build variant mapping first
    image_to_variants = {}
    for variant in product['variants']['edges']:
        variant_node = variant['node']
        if variant_node['image']:
            image_id = variant_node['image']['id']
            if image_id not in image_to_variants:
                image_to_variants[image_id] = []
            variant_info = {
                'variant_id': variant_node['id'],
                'options': [opt for opt in variant_node['selectedOptions']]
            }
            image_to_variants[image_id].append(variant_info)
    manifest = []
    for img in images:
        node = img['node']
        url = node['originalSrc']
        image_id = node['id']
        # Extract original filename from URL
        original_filename = url.split('/')[-1].split('?')[0]  # Remove query parameters
        filename = os.path.join(output_dir, original_filename)
        print(f"Downloading {original_filename}...")
        download_image(url, filename)
        # Include variant associations in manifest
        manifest_entry = {
            'image_id': image_id,
            'original_url': url,
            'original_filename': original_filename,
            'filename': filename,
            'variants': image_to_variants.get(image_id, [])  # List of variants this image is associated with
        }
        manifest.append(manifest_entry)
        # Print variant associations for verification
        if image_to_variants.get(image_id):
            print("  Associated variants:")
            for variant in image_to_variants[image_id]:
                options_str = ", ".join(f"{opt['name']}: {opt['value']}" for opt in variant['options'])
                print(f"    - {options_str}")
        else:
            print("  No variant associations")
    with open('download_manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"\nDownloaded {len(manifest)} images. Manifest saved to download_manifest.json.")
    return manifest

def rename_images(product, download_manifest):
    # Get all option names from variants
    all_option_names = set()
    for variant in product['variants']['edges']:
        for opt in variant['node']['selectedOptions']:
            all_option_names.add(opt['name'])
    option_names = list(all_option_names)
    option_names.sort()
    renamed_manifest = []
    # Group images by variant_id to handle numbering per variant
    variant_image_counts = {}
    # Track the last set of variants for gallery images
    last_variants = []
    last_variant_filenames = {}
    for entry in download_manifest:
        variants = entry['variants']
        if variants:
            last_variants = []
            last_variant_filenames = {}
            # For each variant, duplicate the image and number sequentially
            for variant in variants:
                variant_id = variant['variant_id']
                options = [opt['value'] for opt in variant['options']]
                options_str = "-".join(clean(opt) for opt in options)
                # Initialize counter for this variant if not already done
                if variant_id not in variant_image_counts:
                    variant_image_counts[variant_id] = 1
                else:
                    variant_image_counts[variant_id] += 1
                # Format the counter as a two-digit number (e.g., 01, 02, etc.)
                counter_str = f"{variant_image_counts[variant_id]:02d}"
                # Get the file extension from the original filename
                _, ext = os.path.splitext(entry['original_filename'])
                new_filename = f"{clean(product['title'])}-{options_str}-{counter_str}{ext}"
                # Ensure unique filenames
                base, ext2 = os.path.splitext(new_filename)
                counter = 1
                while os.path.exists(os.path.join("renamed_images", new_filename)):
                    new_filename = f"{base}-{counter}{ext2}"
                    counter += 1
                # Copy the file to the new location
                os.makedirs("renamed_images", exist_ok=True)
                new_path = os.path.join("renamed_images", new_filename)
                with open(entry['filename'], 'rb') as src, open(new_path, 'wb') as dst:
                    dst.write(src.read())
                renamed_manifest.append({
                    **entry,
                    'new_filename': new_filename,
                    'filename': new_path,
                    'gallery_position': variant_image_counts[variant_id],
                    'variant_id': variant_id,
                    'options': options
                })
                # Track for gallery images
                last_variants.append({
                    'variant_id': variant_id,
                    'options': options
                })
                last_variant_filenames[variant_id] = f"{clean(product['title'])}-{options_str}"
        else:
            # If no variants, treat as gallery image for last variants
            if last_variants:
                for variant in last_variants:
                    variant_id = variant['variant_id']
                    options = variant['options']
                    options_str = "-".join(clean(opt) for opt in options)
                    # Use the last variant's filename base
                    filename_base = last_variant_filenames.get(variant_id, f"{clean(product['title'])}-{options_str}")
                    # Increment gallery position for this variant
                    if variant_id not in variant_image_counts:
                        variant_image_counts[variant_id] = 1
                    else:
                        variant_image_counts[variant_id] += 1
                    counter_str = f"{variant_image_counts[variant_id]:02d}"
                    # Get the file extension from the original filename
                    _, ext = os.path.splitext(entry['original_filename'])
                    new_filename = f"{filename_base}-{counter_str}{ext}"
                    # Ensure unique filenames
                    base, ext2 = os.path.splitext(new_filename)
                    counter = 1
                    while os.path.exists(os.path.join("renamed_images", new_filename)):
                        new_filename = f"{base}-{counter}{ext2}"
                        counter += 1
                    # Copy the file to the new location
                    os.makedirs("renamed_images", exist_ok=True)
                    new_path = os.path.join("renamed_images", new_filename)
                    with open(entry['filename'], 'rb') as src, open(new_path, 'wb') as dst:
                        dst.write(src.read())
                    renamed_manifest.append({
                        **entry,
                        'new_filename': new_filename,
                        'filename': new_path,
                        'gallery_position': variant_image_counts[variant_id],
                        'variant_id': variant_id,
                        'options': options
                    })
            else:
                # If no last variants, use a generic name
                new_filename = f"{clean(product['title'])}-{entry['original_filename']}"
                gallery_position = 1
                variant_id = None
                options = []
                # Ensure unique filenames
                base, ext = os.path.splitext(new_filename)
                counter = 1
                while os.path.exists(os.path.join("renamed_images", new_filename)):
                    new_filename = f"{base}-{counter}{ext}"
                    counter += 1
                # Copy the file to the new location
                os.makedirs("renamed_images", exist_ok=True)
                new_path = os.path.join("renamed_images", new_filename)
                with open(entry['filename'], 'rb') as src, open(new_path, 'wb') as dst:
                    dst.write(src.read())
                renamed_manifest.append({
                    **entry,
                    'new_filename': new_filename,
                    'filename': new_path,
                    'gallery_position': gallery_position,
                    'variant_id': variant_id,
                    'options': options
                })
    with open('renamed_manifest.json', 'w') as f:
        json.dump(renamed_manifest, f, indent=2)
    print(f"Renamed {len(renamed_manifest)} images. Manifest saved to renamed_manifest.json.")
    return renamed_manifest, option_names

def search_products(tag=None, vendor=None, title_keyword=None, limit=50):
    query = """
    query searchProducts($query: String!, $first: Int!) {
      products(first: $first, query: $query) {
        edges {
          node {
            id
            handle
            title
            vendor
            tags
          }
        }
      }
    }
    """
    
    # Build the search query
    search_terms = []
    if tag:
        search_terms.append(f"tag:{tag}")
    if vendor:
        search_terms.append(f"vendor:{vendor}")
    if title_keyword:
        search_terms.append(f"title:*{title_keyword}*")
    
    search_query = " AND ".join(search_terms) if search_terms else ""
    variables = {
        "query": search_query,
        "first": limit
    }
    
    data = graphql(query, variables)
    products = data.get('data', {}).get('products', {}).get('edges', [])
    return [edge['node'] for edge in products]

def parse_args():
    parser = argparse.ArgumentParser(description='Process product images for Shopify.')
    parser.add_argument('--product-id', help='Shopify product ID (gid://shopify/Product/...)')
    parser.add_argument('--product-ids', help='Comma-separated list of Shopify product IDs')
    parser.add_argument('--tag', help='Filter products by tag')
    parser.add_argument('--vendor', help='Filter products by vendor')
    parser.add_argument('--title-keyword', help='Filter products by title keyword')
    parser.add_argument('--limit', type=int, default=50, help='Maximum number of products to process')
    return parser.parse_args()

def main():
    args = parse_args()
    
    if args.tag or args.vendor or args.title_keyword:
        print("Searching for products with criteria...")
        # Search for products based on criteria
        products = search_products(
            tag=args.tag,
            vendor=args.vendor,
            title_keyword=args.title_keyword,
            limit=args.limit
        )
        
        if not products:
            print("No products found matching the search criteria.")
            return
            
        print(f"Found {len(products)} products matching the criteria.")
        for product in products:
            print(f"\nProcessing product: {product['title']} (ID: {product['id']})")
            
            # Create product-specific directories
            product_id = product['id'].split('/')[-1]
            download_dir = f"downloaded_images/{product_id}"
            renamed_dir = f"renamed_images/{product_id}"
            os.makedirs(download_dir, exist_ok=True)
            os.makedirs(renamed_dir, exist_ok=True)
            
            print("Getting full product data...")
            # Get full product data
            full_product = get_product_data(product['id'])
            
            print("Downloading images...")
            # Download images
            download_manifest = download_images(full_product, download_dir)
            
            print("Renaming images...")
            # Rename images
            renamed_manifest = rename_images(full_product, download_manifest)
            
            print("Uploading to S3...")
            # Upload to S3
            upload_manifest = upload_images(renamed_manifest)
            
            print("Generating Matrixify CSV...")
            # Generate Matrixify CSV
            option_names = [opt['name'] for opt in full_product['variants']['edges'][0]['node']['selectedOptions']]
            generate_matrixify_csv(full_product, upload_manifest, option_names)
            
            print(f"Completed processing for product: {product['title']}")
    elif args.product_id:
        # Original single product flow
        product_id = args.product_id
        if not product_id.startswith('gid://'):
            product_id = f'gid://shopify/Product/{product_id}'
        product = get_product_data(product_id)
        download_manifest = download_images(product)
        renamed_manifest = rename_images(product, download_manifest)
        upload_manifest = upload_images(renamed_manifest)
        option_names = [opt['name'] for opt in product['variants']['edges'][0]['node']['selectedOptions']]
        generate_matrixify_csv(product, upload_manifest, option_names)
    else:
        print("Error: Please provide either --product-id, --product-ids, or search criteria (--tag, --vendor, --title-keyword)")
        sys.exit(1)

if __name__ == "__main__":
    main()
