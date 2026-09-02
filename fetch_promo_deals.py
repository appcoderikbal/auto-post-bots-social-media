import sys
import random
from dotenv import load_dotenv
from utils import supabase, tg_add_to_queue, tg_is_queued
from amazon_client import search_deals

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')


def fetch_promo_deals():
    print("🔄 Fetching fresh deals via Amazon Creators API...")

    # Only fetch deals in our 3 focused categories
    focused_searches = [
        {"query": "home decor accessories",   "index": "HomeAndKitchen"},
        {"query": "kitchen gadgets tools",    "index": "HomeAndKitchen"},
        {"query": "tech gadgets electronics", "index": "Electronics"},
        {"query": "smart home devices",       "index": "Electronics"},
        {"query": "kitchen appliances",       "index": "HomeAndKitchen"},
        {"query": "home decor living room",   "index": "HomeAndKitchen"},
    ]
    selected = random.choice(focused_searches)
    platforms = ["us", "in"]

    for region in platforms:
        deals = search_deals(selected["query"], search_index=selected["index"], min_saving_percent=20, item_count=10, region=region)
        
        if not deals:
            print(f"No results from Amazon for {region}.")
            continue
            
        count = 0
        target_platform = f"telegram_{region}"
        
        for item in deals:
            asin = item.get("asin")
            if not asin:
                continue

            # Skip if already in queue
            if tg_is_queued(asin, target_platform):
                continue

            tg_add_to_queue(asin, target_platform, category="Promo Deals", product_data=item)

            print(f"✅ Queued Promo Deal ({region}): {asin}")
            count += 1
            if count >= 10:  # Only grab top 10
                break


if __name__ == "__main__":
    fetch_promo_deals()
