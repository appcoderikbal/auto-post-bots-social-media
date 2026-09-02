import os
import sys
import time
import requests
from dotenv import load_dotenv
from utils import tg_get_next_deal, get_deal_caption, tg_delete_deal

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# We expect two channel IDs in the env variables
CHANNELS = {
    "telegram_in": os.getenv("TELEGRAM_CHANNEL_IN"),
    "telegram_us": os.getenv("TELEGRAM_CHANNEL_US")
}

def post_to_telegram(platform):
    channel_id = CHANNELS.get(platform)
    if not channel_id:
        print(f"⚠️ No Telegram channel configured for {platform}.")
        return

    deal = tg_get_next_deal(platform)
    if not deal:
        return

    asin = deal["asin"]
    row_id = deal["id"]
    print(f"🚀 Found queued deal for {platform}: {asin}")

    caption = get_deal_caption(deal, platform=platform)
    image_url = deal.get("image_url")
    
    # Telegram API
    base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    
    try:
        if image_url:
            # Send Photo with caption
            url = f"{base_url}/sendPhoto"
            payload = {
                "chat_id": channel_id,
                "photo": image_url,
                "caption": caption,
                "parse_mode": "HTML" # Fallback if no HTML tags used is fine
            }
        else:
            # Send just text
            url = f"{base_url}/sendMessage"
            payload = {
                "chat_id": channel_id,
                "text": caption,
                "parse_mode": "HTML"
            }
            
        res = requests.post(url, json=payload, timeout=20)
        data = res.json()
        
        if data.get("ok"):
            print(f"✅ Successfully posted {asin} to {platform}!")
            tg_delete_deal(row_id)  # remove from queue immediately
        else:
            print(f"❌ Telegram API Error: {data}")
            # leave in queue to retry next run
            
    except Exception as e:
        print(f"❌ Failed to post {asin} to {platform}: {e}")
        mark_failed(asin, platform)

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN is missing in .env")
        sys.exit(1)
        
    for plat in ["telegram_in", "telegram_us"]:
        post_to_telegram(plat)
        time.sleep(2) # rate limit buffer
