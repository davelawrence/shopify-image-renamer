import json
import csv

# Load the download manifest
with open('download_manifest.json', 'r') as f:
    download_manifest = json.load(f)

# Extract numeric IDs from the download manifest
numeric_ids_from_manifest = set()
for entry in download_manifest:
    # Extract numeric part from image_id
    image_id = entry['image_id']
    numeric_part = image_id.split('/')[-1]
    numeric_ids_from_manifest.add(numeric_part)
    
    # Extract numeric part from variant_id
    for variant in entry['variants']:
        variant_id = variant['variant_id']
        numeric_part = variant_id.split('/')[-1]
        numeric_ids_from_manifest.add(numeric_part)

# Load the CSV file
csv_ids = set()
with open('matrixify-import-batch.csv', 'r') as f:
    reader = csv.reader(f)
    next(reader)  # Skip header
    for row in reader:
        if row:
            csv_ids.add(row[0])

# Compare the IDs
missing_in_csv = numeric_ids_from_manifest - csv_ids
extra_in_csv = csv_ids - numeric_ids_from_manifest

print("Numeric IDs from download manifest:", numeric_ids_from_manifest)
print("Numeric IDs from CSV:", csv_ids)
print("IDs missing in CSV:", missing_in_csv)
print("Extra IDs in CSV:", extra_in_csv)

# Count unique product IDs in the CSV
print("Number of unique product IDs in CSV:", len(csv_ids))

# Original list of 67 product IDs
original_list = {
    '9700267262249', '9700267295017', '9700294164777', '9700267327785', '9700267360553', '9700297212201',
    '9700267393321', '9700267426089', '9700267458857', '9700267491625', '9700267524393', '9700267557161',
    '9700267589929', '9700267622697', '9700267655465', '9700267688233', '9700267753769', '9700267786537',
    '9700267819305', '9700267852073', '9700267917609', '9700267950377', '9700267983145', '9700268015913',
    '9700268048681', '9700268081449', '9700268146985', '9700268179753', '9700268212521', '9700268278057',
    '9700268310825', '9700268343593', '9700268376361', '9700268409129', '9700268474665', '9700268507433',
    '9700268572969', '9700268605737', '9700268671273', '9700268704041', '9700268769577', '9700268802345',
    '9700268867881', '9700268900649', '9700268966185', '9700268998953', '9700269064489', '9700269097257',
    '9699474571561', '9699474604329', '9699474637097', '9700269162793', '9700269195561', '9700269261097',
    '9700269293865', '9700269359401', '9700269392169', '9700308255017', '9687370793257', '9687370957097',
    '9687371055401', '9687371219241', '9687371284777', '9687371383081', '9700269785385', '9700269818153',
    '9700269883689'
}

# Identify missing product IDs
missing_product_ids = original_list - csv_ids
print("Missing product IDs:", missing_product_ids) 