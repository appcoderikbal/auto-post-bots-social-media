import sys
import random
from dotenv import load_dotenv
from utils import supabase, add_to_queue
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
    deals = search_deals(selected["query"], search_index=selected["index"], min_saving_percent=20, item_count=10)

    if not deals:
        print("No results from Amazon (Creators API + fallback).")
        return

    print(f"✨ Found {len(deals)} potential deals.")

    platforms = ["fb", "ig"]
    count = 0

    for item in deals:
        asin = item.get("asin")
        if not asin:
            continue

        # Check if already exists in queue
        existing = supabase.table("deals_queue").select("id").eq("asin", asin).execute()
        if len(existing.data) > 0:
            continue

        # Add to queue (image URLs are intentionally not persisted; see utils.add_to_queue)
        target_platform = random.choice(platforms)
        add_to_queue(asin, target_platform, category="Promo Deals", product_data=item)

        print(f"✅ Queued Promo Deal: {asin}")
        count += 1
        if count >= 10:  # Only grab top 10
            break


if __name__ == "__main__":
    fetch_promo_deals()
