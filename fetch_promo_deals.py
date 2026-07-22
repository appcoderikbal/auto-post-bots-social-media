import sys
import random
from dotenv import load_dotenv
from utils import supabase, add_to_queue
from amazon_client import search_deals

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')


def fetch_promo_deals():
    print("🔄 Fetching fresh deals via Amazon Creators API...")

    # Keywords likely to surface discounted items; PA-API filters by min saving.
    query = random.choice(["deals", "today's deals", "best sellers", "top rated"])
    deals = search_deals(query, search_index="All", min_saving_percent=20, item_count=10)

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
