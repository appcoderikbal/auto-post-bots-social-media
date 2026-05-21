import os
import requests
import sys
import random
import urllib.parse
from dotenv import load_dotenv
from utils import supabase, add_to_queue

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "amazon-data-scraper-api3.p.rapidapi.com")
AMAZON_ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "dealducker09-20")

def fetch_promo_deals():
    print("🔄 Fetching fresh deals using primary API...")
    
    url = f"https://{RAPIDAPI_HOST}/queries"
    
    # We search for terms likely to yield high discounts or promo items
    query = random.choice(["lightning deals", "today's deals", "deal of the day 80% off", "amazon promo codes active"])
    
    payload = {"source": "amazon_search", "query": query, "geo_location": "90210", "parse": True}
    headers = {"content-type": "application/json", "X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST}

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            print(f"❌ API Error: {response.status_code} - {response.text}")
            return
            
        res = response.json()
        results_list = res.get("results", [])
        if not results_list:
            print("No results from API.")
            return

        content = results_list[0].get("content", {})
        organic = content.get("results", {}).get("organic", []) or content.get("organic", [])

        if not organic:
            print("No organic results found.")
            return

        print(f"✨ Found {len(organic)} potential deals.")
        
        platforms = ["fb", "ig"]
        count = 0
        
        for item in organic:
            asin = item.get("asin")
            if not asin:
                continue
                
            # Check if already exists in queue
            existing = supabase.table("deals_queue").select("id").eq("asin", asin).execute()
            if len(existing.data) > 0:
                continue

            base_product_url = f"https://www.amazon.com{item.get('url')}"
            parsed_url = urllib.parse.urlparse(base_product_url)
            separator = '&' if parsed_url.query else '?'
            affiliate_url = f"{base_product_url}{separator}tag={AMAZON_ASSOCIATE_TAG}"
            
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
            
            # Add to queue
            target_platform = random.choice(platforms)
            add_to_queue(asin, target_platform, category="Promo Deals", product_data=product_data)
            
            print(f"✅ Queued Promo Deal: {asin}")
            count += 1
            if count >= 10: # Only grab top 10
                break
                
    except Exception as e:
        print(f"❌ Error in fetch_promo_deals: {e}")

if __name__ == "__main__":
    fetch_promo_deals()
