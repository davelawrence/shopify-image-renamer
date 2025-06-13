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

# GraphQL query to get products with specific vendor and tag
query = """
query getProducts($query: String!) {
  products(first: 250, query: $query) {
    edges {
      node {
        id
        title
        handle
        vendor
        tags
      }
    }
  }
}
"""

# Search query for BDi vendor and VRF New tag
search_query = 'vendor:BDi AND tag:"VRF New"'
variables = {"query": search_query}

response = requests.post(API_URL, json={"query": query, "variables": variables}, headers=HEADERS)

if response.status_code == 200:
    data = response.json()
    products = data['data']['products']['edges']
    print(f"\nFound {len(products)} products matching vendor:BDi AND tag:'VRF New'")
    print("\nProduct details:")
    for product in products:
        node = product['node']
        print(f"\nTitle: {node['title']}")
        print(f"Handle: {node['handle']}")
        print(f"ID: {node['id']}")
        print(f"Vendor: {node['vendor']}")
        print(f"Tags: {node['tags']}")
else:
    print(f"Error: {response.text}") 