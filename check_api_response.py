import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
API_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN")

if not SHOPIFY_STORE or not API_TOKEN:
    print("Error: Required environment variables SHOPIFY_STORE and SHOPIFY_ADMIN_API_TOKEN must be set")
    exit(1)

HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": API_TOKEN
}

API_URL = f"https://{SHOPIFY_STORE}/admin/api/2023-10/graphql.json"

# Missing product IDs
missing_product_ids = [
    '9700297212201',
    '9700269785385',
    '9700308255017',
    '9700294164777',
    '9700269883689',
    '9700269818153'
]

# GraphQL query to get product data
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

# Check API response for each missing product ID
for product_id in missing_product_ids:
    variables = {"id": f"gid://shopify/Product/{product_id}"}
    response = requests.post(API_URL, json={"query": query, "variables": variables}, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        print(f"\nAPI Response for Product ID {product_id}:")
        print(json.dumps(data, indent=2))
    else:
        print(f"\nError fetching data for Product ID {product_id}: {response.text}") 