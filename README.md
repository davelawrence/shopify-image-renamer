# Shopify Image Renamer

This application automates the process of downloading, renaming, and re-uploading product images for Shopify products. It ensures correct variant mapping and gallery order by generating a Matrixify-compatible CSV file.

## Features

- Downloads product images from Shopify.
- Renames images according to a specific format, including all variant options.
- Uploads images to AWS S3 and retrieves public URLs.
- Generates a Matrixify-compatible CSV for bulk import.
- Supports processing multiple products based on tags, vendor, and title keywords.
- Includes S3 bucket cleanup functionality to manage storage.
- Modular, CLI-driven workflow for robust testing and automation.

## Prerequisites

- Python 3.6 or higher.
- Shopify Admin API access token.
- Shopify store URL.
- AWS S3 bucket for image hosting.

## Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd shopify-image-renamer
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root with the following variables:
   ```
   SHOPIFY_STORE=your-store.myshopify.com
   SHOPIFY_ADMIN_API_TOKEN=your-api-token
   # Optional: Default PRODUCT_ID if not provided via command line
   PRODUCT_ID=gid://shopify/Product/your-product-id
   # AWS S3 credentials for image hosting
   AWS_ACCESS_KEY_ID=your-aws-access-key-id
   AWS_SECRET_ACCESS_KEY=your-aws-secret-access-key
   AWS_S3_BUCKET=your-s3-bucket-name
   AWS_S3_REGION=your-s3-region
   ```

## Version Control

The repository is set up to ignore temporary and generated files:
- `downloaded_images/`: Contains downloaded product images
- `renamed_images/`: Contains renamed images ready for upload
- `*.json`: Manifest files generated during the process
- `*.csv`: Generated Matrixify import files
- `*.jpg`: Image files
- `.DS_Store`: macOS system files

Only source code and documentation are tracked in version control.

## Usage

### Command Line Arguments

- `--product-id`: Optional. Shopify Product ID (e.g., 9660968927529). If not provided, uses PRODUCT_ID from .env
- `--product-ids`: Optional. Comma-separated list of Shopify Product IDs
- `--tag`: Optional. Filter products by tag
- `--vendor`: Optional. Filter products by vendor
- `--title-keyword`: Optional. Filter products by title keyword
- `--limit`: Optional. Maximum number of products to process (default: 50)
- `--clean-s3`: Optional. Enable S3 bucket cleanup
- `--s3-prefix`: Optional. Only delete S3 objects with this prefix
- `--s3-days-old`: Optional. Only delete S3 objects older than this many days

### Processing Multiple Products

You can process multiple products at once using search criteria:

```bash
# Process all products with tag "VRF New" from vendor "Stressless" containing "recliner" in the title
python image-renamer.py --tag "VRF New" --vendor "Stressless" --title-keyword "recliner"

# Process up to 5 products with tag "VRF New"
python image-renamer.py --tag "VRF New" --limit 5
```

When processing multiple products:
- Images are organized in product-specific directories
- A single combined Matrixify CSV is generated with a descriptive filename
- The CSV includes all products with their respective variant images

### S3 Bucket Cleanup

Manage your S3 storage with flexible cleanup options:

```bash
# Clean all objects in the S3 bucket
python image-renamer.py --clean-s3

# Clean only objects with a specific prefix
python image-renamer.py --clean-s3 --s3-prefix "sunrise-recliner"

# Clean only objects older than 30 days
python image-renamer.py --clean-s3 --s3-days-old 30

# Combine with other operations
python image-renamer.py --tag "VRF New" --clean-s3 --s3-days-old 7
```

### Single Product Processing

For processing a single product:

```bash
# Process a single product by ID
python image-renamer.py --product-id 9660968927529

# Process multiple specific products
python image-renamer.py --product-ids "9660968927529,9660968927530"
```

### Modular Pipeline Stages

You can run the workflow in modular stages for testing, or all at once for automation.

#### Run a Single Stage (with optional confirmation):
```bash
python image-renamer.py --stage download --product-id 9660968927529 --confirm
python image-renamer.py --stage rename --product-id 9660968927529 --confirm
python image-renamer.py --stage upload --product-id 9660968927529 --confirm
python image-renamer.py --stage generate-csv --product-id 9660968927529 --confirm
```

#### Run All Stages in Sequence (for production):
```bash
python image-renamer.py --stage all --product-id 9660968927529
```

- The `--confirm` flag will pause after each stage so you can verify outputs before proceeding.
- Intermediate artifacts (JSON manifests) are saved after each stage, so you can inspect or resume from any step.

### Intermediate Artifacts
- `download_manifest.json`: List of downloaded images and their original URLs.
- `renamed_manifest.json`: List of renamed images and their variant associations.
- `upload_manifest.json`: List of uploaded images and their S3 URLs.
- `matrixify-import-<product-title>.csv`: The final CSV for Matrixify import, with the product title in the filename.

## Development & Testing Best Practices

- The script is modular and each stage can be run independently for robust testing.
- You can inspect intermediate files to verify correctness before moving to the next step.
- For new product types or catalog changes, use the `--confirm` flag to layer in manual verification.
- When satisfied, run the full pipeline automatically for efficiency.

## Workflow

1. **Cleanup**: The script automatically cleans up files from previous runs and optionally cleans the S3 bucket.
2. **Download and Rename**: Images are downloaded and renamed based on variant options.
3. **Upload to AWS S3**: Images are uploaded to AWS S3, and public URLs are retrieved.
4. **Generate CSV with Global Gallery Order**: The script generates a Matrixify CSV where all images are assigned a unique, sequential Image Position. For each variant, the mapped image is first (with Variant ID), and any additional images for that variant immediately follow as product-level images. Images not mapped to any variant are added at the end. This ensures Shopify/Matrixify treat these as a "variant gallery" in the correct order.
5. **Matrixify Import**: Use the generated CSV to import images into Shopify. The first image uses the REPLACE command (removing all existing images), and all others use MERGE, ensuring a full image refresh and correct gallery order.

### Shopify Gallery Order Note

Shopify does not have a true "variant gallery". Instead, the first image for a variant is mapped to the variant, and any additional images for that variant must immediately follow in the product gallery order as product-level images. This script ensures that all images for a variant are grouped together in the correct order, so Shopify displays them as a logical gallery for each variant.

## Notes

- The script automatically cleans up files from previous runs before starting.
- You can use S3 cleanup to manage storage and stay within free tier limits.
- When processing multiple products, a single combined CSV is generated with a descriptive filename based on the search criteria.
- The script does not delete existing images; this is handled by Matrixify during the import process.
- Only the first image for each variant is mapped to the variant; additional images appear in the gallery but are not variant-specific.
- If a single image is mapped to multiple variants, the script duplicates and renames it for each variant association, ensuring unique filenames and URLs.
- The script dynamically handles any number of variant options (future-proof for Shopify changes).

## Troubleshooting

- If you see an error like `"Variant ID" [gid://shopify/ProductVariant/50200915214633] must be a number`, ensure your CSV contains only the numeric part of the Variant ID (e.g., `50200915214633`). The script now handles this automatically.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 