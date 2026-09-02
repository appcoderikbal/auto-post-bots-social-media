import sys
import random
from dotenv import load_dotenv
from utils import tg_add_to_queue
from amazon_client import search_deals

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')


def refresh_deals():
    # Only post deals in these 3 focused categories
    categories = [
        {"query": "home decor accessories",         "name": "Home Decor",    "index": "HomeAndKitchen"},
        {"query": "home decor wall art living room", "name": "Home Decor",    "index": "HomeAndKitchen"},
        {"query": "kitchen gadgets tools",           "name": "Kitchen",       "index": "HomeAndKitchen"},
        {"query": "kitchen appliances useful",       "name": "Kitchen",       "index": "HomeAndKitchen"},
        {"query": "tech gadgets electronics",        "name": "Tech Gadgets",  "index": "Electronics"},
        {"query": "smart home devices gadgets",      "name": "Tech Gadgets",  "index": "Electronics"},
    ]

    # Pick a random category to refresh
    selected = random.choice(categories)
    query = selected["query"]
    category_name = selected["name"]
    search_index = selected["index"]

    print(f"Refreshing deals for category: '{category_name}' (Query: '{query}')...")

    platforms = ["us", "in"]
    for region in platforms:
        deals = search_deals(query, search_index=search_index, min_saving_percent=15, item_count=10, region=region)

        if not deals:
            print(f"No results from Creators API for {region}.")
            continue

        count = 0
        target_platform = f"telegram_{region}"
        for item in deals:
            asin = item.get("asin")
            if not asin:
                continue
            tg_add_to_queue(asin, target_platform, category=category_name, product_data=item)
            count += 1

        print(f"Success! Syncing {count} fresh deals from {category_name} ({region}) to Supabase!")


if __name__ == "__main__":
    refresh_deals()
