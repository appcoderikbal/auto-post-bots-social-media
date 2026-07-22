import sys
import random
from dotenv import load_dotenv
from utils import add_to_queue
from amazon_client import search_deals

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')


def refresh_deals():
    # Category list for broader deal selection (query + Creators API search index)
    categories = [
        {"query": "deals", "name": "Hot Deals", "index": "All"},
        {"query": "tech gadgets electronics", "name": "Tech Gadgets", "index": "Electronics"},
        {"query": "home appliances kitchen", "name": "Home Appliances", "index": "HomeAndKitchen"},
        {"query": "best selling", "name": "Hot Deals", "index": "All"},
        {"query": "gaming accessories", "name": "Gaming", "index": "VideoGames"},
        {"query": "smart home devices", "name": "Smart Home", "index": "Electronics"},
    ]

    # Pick a random category to refresh
    selected = random.choice(categories)
    query = selected["query"]
    category_name = selected["name"]
    search_index = selected["index"]

    print(f"Refreshing deals for category: '{category_name}' (Query: '{query}')...")

    deals = search_deals(query, search_index=search_index, min_saving_percent=15, item_count=10)

    if not deals:
        print("No results from Creators API.")
        return

    count = 0
    for item in deals:
        asin = item.get("asin")
        if not asin:
            continue
        # Image URLs are intentionally not persisted; see utils.add_to_queue.
        target_platform = random.choice(["fb", "ig"])
        add_to_queue(asin, target_platform, category=category_name, product_data=item)
        count += 1

    print(f"Success! Syncing {count} fresh deals from {category_name} to Supabase!")


if __name__ == "__main__":
    refresh_deals()
