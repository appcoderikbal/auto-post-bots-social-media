"""
run_bot.py — Single entry point for GitHub Actions cron.

Triggered every hour. Posts one deal to each Telegram channel
if the current time falls within the allowed window:
  - USA  (@snagpopofficial) : 8 AM – 1 AM  EST  (America/New_York)
  - IN   (@snagpop)         : 8 AM – 1 AM  IST  (Asia/Kolkata)

Flow per region:
  1. Check posting window — skip if outside hours.
  2. Check telegram_queue DB — use the oldest queued deal if available.
  3. If queue is empty — fetch a fresh deal from Amazon API on-the-fly.
  4. Post to Telegram → delete from queue (or do nothing on failure).
"""

import os
import sys
import random
import time
import requests
from datetime import datetime
import pytz
from dotenv import load_dotenv

from amazon_client import search_deals
from utils import tg_get_mixed_deals, tg_delete_deal, tg_add_to_queue, tg_is_queued, get_deal_caption, save_product_link, cleanup_old_product_links, is_recently_processed

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

# ── Config ────────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

REGIONS = {
    "telegram_us": {
        "channel":   os.getenv("TELEGRAM_CHANNEL_US", "@snagpopofficial"),
        "timezone":  "America/New_York",   # EST/EDT
        "region":    "us",
    },
    "telegram_in": {
        "channel":   os.getenv("TELEGRAM_CHANNEL_IN", "@snagpop"),
        "timezone":  "Asia/Kolkata",       # IST
        "region":    "in",
    },
}

SEARCH_CATEGORIES = [
    {"query": "home decor accessories",         "index": "HomeAndKitchen"},
    {"query": "kitchen gadgets tools",          "index": "HomeAndKitchen"},
    {"query": "tech gadgets electronics",       "index": "Electronics"},
    {"query": "smart home devices",             "index": "Electronics"},
    {"query": "kitchen appliances",             "index": "HomeAndKitchen"},
    {"query": "home decor living room",         "index": "HomeAndKitchen"},
]

# Posting window: 8 AM (inclusive) → 1 AM next day (exclusive)
WINDOW_START = 8   # 08:00 local time
WINDOW_END   = 1   # 01:00 local time (next day — crosses midnight)


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_in_window(timezone_str: str) -> bool:
    """Return True if local time in timezone_str is within posting window."""
    tz  = pytz.timezone(timezone_str)
    now = datetime.now(tz)
    h   = now.hour
    # Window crosses midnight: valid if hour >= 8 OR hour < 1
    in_window = (h >= WINDOW_START) or (h < WINDOW_END)
    print(f"  🕐 Local time ({timezone_str}): {now.strftime('%H:%M')} — "
          f"{'✅ within window' if in_window else '⏭️ outside window (8 AM–1 AM)'}")
    return in_window


def fetch_fresh_deal(region: str) -> dict | None:
    """Fetch one deal from Amazon on-the-fly (used when queue is empty)."""
    cat = random.choice(SEARCH_CATEGORIES)
    print(f"  📡 Queue empty — fetching fresh deal: '{cat['query']}' ({region.upper()})")
    deals = search_deals(
        cat["query"],
        search_index=cat["index"],
        min_saving_percent=15,
        item_count=10,
        region=region,
    )
    if not deals:
        print("  ⚠️ Amazon returned no deals.")
        return None
        
    for deal in deals:
        if not tg_is_queued(deal.get("asin"), f"telegram_{region}") and not is_recently_processed(deal.get("asin"), region):
            # Save the affiliate link for the website
            save_product_link(deal.get("asin"), region, deal.get("affiliate_url"), deal.get("title"))
            return deal
            
    print("  ⚠️ All fetched live deals were recently processed or queued.")
    return None


def send_to_telegram(channel: str, deal: dict, platform: str) -> bool:
    """Post a deal to a Telegram channel. Returns True on success."""
    caption   = get_deal_caption(deal, platform=platform)
    image_url = deal.get("image_url")
    base_url  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    if image_url:
        url     = f"{base_url}/sendPhoto"
        payload = {"chat_id": channel, "photo": image_url,
                   "caption": caption, "parse_mode": "HTML"}
    else:
        url     = f"{base_url}/sendMessage"
        payload = {"chat_id": channel, "text": caption, "parse_mode": "HTML"}

    try:
        res  = requests.post(url, json=payload, timeout=20)
        data = res.json()
        if data.get("ok"):
            print(f"  ✅ Posted to {channel}!")
            return True
        print(f"  ❌ Telegram API error: {data.get('description')}")
    except Exception as e:
        print(f"  ❌ Request failed: {e}")
    return False


def is_last_hour(timezone_str: str) -> bool:
    """Return True if it is the last posting hour of the day (midnight, 00:xx)."""
    tz  = pytz.timezone(timezone_str)
    now = datetime.now(tz)
    return now.hour == 0  # 12:00 AM — last valid hour before 1 AM cutoff


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN missing in .env")
        sys.exit(1)
        
    # Clean up product links older than 3 days
    cleanup_old_product_links(days=3)

    for platform, cfg in REGIONS.items():
        print(f"\n{'─'*50}")
        print(f"🌍 Platform : {platform}  →  {cfg['channel']}")

        # 1. Time window check
        if not is_in_window(cfg["timezone"]):
            continue

        last_hour = is_last_hour(cfg["timezone"])
        if last_hour:
            print("  🌙 Last posting hour — flushing all remaining queued deals...")

        # ── End-of-day flush: post every remaining DB deal ────────────────────
        if last_hour:
            flushed = 0
            while True:
                deals = tg_get_mixed_deals(platform, count=10)
                if not deals:
                    break
                for deal in deals:
                    row_id = deal["id"]
                    print(f"  📦 Flushing: {deal.get('title', deal.get('asin'))}")
                    success = send_to_telegram(cfg["channel"], deal, platform)
                    if success:
                        tg_delete_deal(row_id)
                        flushed += 1
                    else:
                        print("  🗑️ Deleting failed deal to keep queue clean for tomorrow.")
                        tg_delete_deal(row_id)
                    time.sleep(3)  # avoid Telegram rate limit

            print(f"  ✅ Flushed {flushed} deal(s) for {platform}. Queue is now clean.")

        # ── Normal hour: post 3-4 mixed deals ────────────
        else:
            num_posts = random.randint(3, 4)
            print(f"  🎯 Target posts for this hour: {num_posts}")
            
            # Get up to num_posts mixed deals from DB
            db_deals = tg_get_mixed_deals(platform, count=num_posts)
            posted_count = 0
            
            for deal in db_deals:
                row_id = deal["id"]
                print(f"  📦 Using queued deal: {deal.get('title', deal.get('asin'))}")
                success = send_to_telegram(cfg["channel"], deal, platform)
                if success:
                    tg_delete_deal(row_id)
                    print(f"  🗑️ Removed from queue (row {row_id})")
                    posted_count += 1
                time.sleep(3)
                
            # If we didn't have enough in DB, fill the rest with live Amazon fetches
            while posted_count < num_posts:
                print(f"  📡 Not enough deals in queue. Fetching live deal...")
                live_deal = fetch_fresh_deal(cfg["region"])
                if live_deal:
                    success = send_to_telegram(cfg["channel"], live_deal, platform)
                    if success:
                        posted_count += 1
                else:
                    print(f"  ⚠️ No live deals available right now.")
                    break
                time.sleep(3)
                
            print(f"  ✅ Posted {posted_count}/{num_posts} deals for {platform}")

        time.sleep(2)  # buffer between channels

    print(f"\n{'─'*50}")
    print("✅ Bot run complete.")


if __name__ == "__main__":
    run()
