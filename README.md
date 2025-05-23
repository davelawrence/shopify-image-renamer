# Shopify Image Renamer

This application automates the process of downloading, renaming, and re-uploading product images for Shopify products. It ensures correct variant mapping and gallery order by generating a Matrixify-compatible CSV file.

## Features

- Downloads product images from Shopify.
- Renames images according to a specific format.
- Uploads images to Shopify Files and retrieves public URLs.
- Generates a Matrixify-compatible CSV for bulk import.

## Prerequisites

- Python 3.6 or higher.
- Shopify Admin API access token.
- Shopify store URL.

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
   PRODUCT_ID=gid://shopify/Product/your-product-id
   ```

## Usage

Run the script to process images:
```bash
python image-renamer.py
```

The script will:
- Download images from the specified Shopify product.
- Rename them according to the variant options.
- Upload them to Shopify Files.
- Generate a CSV file (`matrixify-import.csv`) for Matrixify import.

## Workflow

1. **Download and Rename**: Images are downloaded and renamed based on variant options.
2. **Upload to Shopify Files**: Images are uploaded to Shopify Files, and public URLs are retrieved.
3. **Generate CSV**: A CSV file is created with the necessary fields for Matrixify import.
4. **Matrixify Import**: Use the generated CSV to import images into Shopify, ensuring correct variant mapping and gallery order.

## Notes

- The script does not delete existing images; this is handled by Matrixify during the import process.
- Only the first image for each variant is mapped to the variant; additional images appear in the gallery but are not variant-specific.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 