import json
import csv
import os

def clean(text):
    # Remove pipes, extra dashes, and clean up the text
    cleaned = text.lower().replace("|", " ").replace("/", "-").replace(",", "").replace("&", "and").replace("+", "-")
    cleaned = cleaned.replace(" ", "-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-")
    return cleaned

def generate_csv_from_manifest():
    # Read the upload manifest
    with open('upload_manifest.json', 'r') as f:
        upload_manifest = json.load(f)
    
    # Group images by product ID
    product_images = {}
    for entry in upload_manifest:
        # Extract product ID from variant ID
        variant_id = entry['variant_id']
        if variant_id:
            # Extract product ID from variant ID (format: gid://shopify/ProductVariant/PRODUCT_ID/VARIANT_ID)
            parts = variant_id.split('/')
            if len(parts) >= 4:
                product_id = parts[-2]  # Get the product ID from the variant ID
                if product_id not in product_images:
                    product_images[product_id] = []
                product_images[product_id].append(entry)
    
    # Generate CSV rows
    all_csv_rows = []
    for product_id, images in product_images.items():
        # Sort images by gallery position
        images.sort(key=lambda x: x.get('gallery_position', 0))
        
        # Get option names from the first image's variants
        option_names = []
        if images and images[0].get('variants'):
            option_names = [opt['name'] for opt in images[0]['variants'][0]['options']]
        
        # Generate rows for each image
        for idx, entry in enumerate(images, 1):
            row = {
                'ID': product_id,
                'Handle': clean(entry['new_filename'].split('-')[0]),  # Extract handle from filename
                'Image Type': 'IMAGE',
                'Image Src': entry['file_url'],
                'Image Command': 'REPLACE' if idx == 1 else 'MERGE',
                'Image Position': idx,
                'Variant ID': entry['variant_id'].split('/')[-1] if entry.get('variant_id') else '',
            }
            
            # Add option names and values
            for i, name in enumerate(option_names):
                row[f'Option{i+1} Name'] = name
                row[f'Option{i+1} Value'] = entry['options'][i] if i < len(entry['options']) else ''
            
            # Set Variant Image URL only for the first image of each variant
            row['Variant Image'] = entry['file_url'] if idx == 1 else ''
            
            all_csv_rows.append(row)
    
    # Write CSV file
    csv_filename = "matrixify-import-batch.csv"
    if all_csv_rows:
        fieldnames = list(all_csv_rows[0].keys())
        with open(csv_filename, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in all_csv_rows:
                writer.writerow(row)
        print(f"Successfully wrote {len(all_csv_rows)} rows to {csv_filename}")
    else:
        print("No CSV rows generated.")

if __name__ == "__main__":
    generate_csv_from_manifest() 