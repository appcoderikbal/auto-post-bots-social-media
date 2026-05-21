import requests
import os
import urllib.parse
import random
import sys
from dotenv import load_dotenv
from utils import add_to_queue

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

AMAZON_ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "dealducker09-20")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "amazon-data-scraper-api3.p.rapidapi.com")

def refresh_deals():
    # Category list for broader deal selection
    categories = [
        {"query": "amazon promo codes active deals", "name": "Promo Codes"},
        {"query": "tech gadgets electronics deals", "name": "Tech Gadgets"},
        {"query": "home appliances kitchen deals", "name": "Home Appliances"},
        {"query": "best selling discounted deals", "name": "Hot Deals"},
        {"query": "gaming accessories deals", "name": "Gaming"},
        {"query": "smart home devices deals", "name": "Smart Home"}
    ]
    
    # Pick a random category to refresh
    selected = random.choice(categories)
    query = selected["query"]
    category_name = selected["name"]
    
    print(f"Refreshing deals for category: '{category_name}' (Query: '{query}')...")
    
    url = f"https://{RAPIDAPI_HOST}/queries"
    payload = {"source": "amazon_search", "query": query, "geo_location": "90210", "parse": True}
    headers = {"content-type": "application/json", "X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST}
    
    try:
        res = requests.post(url, json=payload, headers=headers).json()
        results_list = res.get("results", [])
        if not results_list: 
            print("No results from API.")
            return

        content = results_list[0].get("content", {})
        organic = content.get("results", {}).get("organic", []) or content.get("organic", [])

        if organic:
            # Distribute deals across platforms
            count = 0
            for item in organic:
                asin = item.get("asin")
                if not asin: continue
                
                # Format product data for the website
                base_product_url = f"https://www.amazon.com{item.get('url')}"
                parsed_url = urllib.parse.urlparse(base_product_url)
                separator = '&' if parsed_url.query else '?'
                affiliate_url = f"{base_product_url}{separator}tag={AMAZON_ASSOCIATE_TAG}"
                
                # Calculate discount
                price = item.get('price', 0)
                old_price = item.get('price_strikethrough', 0)
                discount = None
                if old_price and price and old_price > price:
                    discount = f"{round((old_price - price) / old_price * 100)}%"

                product_data = {
                    "title": item.get("title"),
                    "price": f"${price}" if price else "Check price",
                    "old_price": f"${old_price}" if old_price else None,
                    "discount": discount,
                    "image_url": item.get("url_image"),
                    "affiliate_url": affiliate_url,
                    "rating": item.get("rating"),
                    "reviews_count": item.get("reviews_count")
                }
                
                target_platform = random.choice(["fb", "ig"])
                add_to_queue(asin, target_platform, category=category_name, product_data=product_data)
                count += 1
            print(f"Success! Syncing {count} fresh deals from {category_name} to Supabase!")
        else:
            print("No new unique ASINs found in search results.")
    except Exception as e:
        print(f"Error refreshing deals: {e}")

if __name__ == "__main__":
    refresh_deals()
