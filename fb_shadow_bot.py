import os
import re
import time
import json
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from utils import get_deal_caption, supabase

import sys
load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

# Config
TARGET_PAGE_URL = "https://www.facebook.com/people/Ellas-BEST-DEALS/100088696640548/"
HISTORY_FILE = "shadow_bot_history.json"
AMAZON_ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "dealducker09-20")

# API Config for Posting (Imported or Re-implemented for direct use)
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
IG_USER_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "amazon-data-scraper-api3.p.rapidapi.com")

def resolve_asin(url):
    """Follows redirects to find the final Amazon ASIN"""
    try:
        print(f"🔗 Resolving link: {url}")
        res = requests.get(url, allow_redirects=True, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        final_url = res.url
        print(f"📍 Final URL: {final_url}")
        
        # Pattern 1: /dp/ASIN
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', final_url)
        if asin_match: return asin_match.group(1)
        
        # Pattern 2: /gp/product/ASIN
        asin_match = re.search(r'/gp/product/([A-Z0-9]{10})', final_url)
        if asin_match: return asin_match.group(1)
        
        # Pattern 3: asin=ASIN (query param)
        asin_match = re.search(r'asin=([A-Z0-9]{10})', final_url)
        if asin_match: return asin_match.group(1)
        
    except Exception as e:
        print(f"❌ Error resolving link: {e}")
    return None

def get_product_details(asin):
    """Fetches high-quality data for the ASIN from Amazon API"""
    print(f"🔍 Fetching official data for ASIN: {asin}")
    url = f"https://{RAPIDAPI_HOST}/queries"
    payload = {"source": "amazon_product", "query": asin, "geo_location": "90210", "parse": True}
    headers = {"content-type": "application/json", "X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST}
    try:
        response = requests.post(url, json=payload, headers=headers).json()
        content = response.get("results", [])[0].get("content", {})
        if not content: return None
        return {
            "asin": asin,
            "title": content.get("title"),
            "price": f"${content.get('price')}" if content.get('price') else "Check price",
            "discount_text": f" ({content.get('discount_percentage')}% OFF!)" if content.get('discount_percentage') else "",
            "image_list": content.get("images", [])[:5],
            "rating": content.get("rating"),
            "reviews_count": content.get("reviews_count")
        }
    except Exception as e:
        print(f"❌ API Error: {e}")
        return None

def post_to_facebook(deal, promo_code):
    print("📤 Posting to Facebook...")
    caption = get_deal_caption(deal, platform="fb")
    if promo_code:
        caption = f"🔥 PROMO CODE: {promo_code}\n\n" + caption
    
    try:
        # Upload images as unpublished first
        photo_ids = []
        for img_url in deal['image_list']:
            res = requests.post(f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos", 
                                data={'url': img_url, 'published': 'false', 'access_token': FB_ACCESS_TOKEN}).json()
            if 'id' in res: photo_ids.append(res['id'])
        
        attached_media = json.dumps([{"media_fbid": pid} for pid in photo_ids])
        result = requests.post(f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed", 
                               data={'message': caption, 'attached_media': attached_media, 'access_token': FB_ACCESS_TOKEN}).json()
        
        if 'id' in result:
            print(f"✅ Posted to FB: {result['id']}")
            # Add Pinned Comment
            tracker_url = f"https://www.snagpop.com/l/{deal['asin']}?s=fb"
            requests.post(f"https://graph.facebook.com/v19.0/{result['id']}/comments", 
                          data={'message': f"🛒 Grab it here: {tracker_url}", 'access_token': FB_ACCESS_TOKEN})
            return True
    except Exception as e:
        print(f"❌ FB Error: {e}")
    return False

def post_to_instagram(deal, promo_code):
    print("📤 Posting to Instagram...")
    caption = get_deal_caption(deal, platform="ig")
    if promo_code:
        caption = f"🔥 CODE: {promo_code}\n\n" + caption
        
    try:
        # Step 1: Create Item Containers
        container_ids = []
        for img_url in deal['image_list']:
            res = requests.post(f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media",
                                data={'image_url': img_url, 'is_carousel_item': 'true', 'access_token': FB_ACCESS_TOKEN}).json()
            if 'id' in res: container_ids.append(res['id'])
        
        # Step 2: Create Carousel
        res = requests.post(f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media",
                            data={'caption': caption, 'media_type': 'CAROUSEL', 'children': ','.join(container_ids), 'access_token': FB_ACCESS_TOKEN}).json()
        
        if 'id' in res:
            requests.post(f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish", 
                          data={'creation_id': res['id'], 'access_token': FB_ACCESS_TOKEN})
            print("✅ Posted to Instagram!")
            return True
    except Exception as e:
        print(f"❌ IG Error: {e}")
    return False

def post_to_telegram(deal, promo_code):
    print("📤 Posting to Telegram...")
    caption = get_deal_caption(deal, platform="tg")
    if promo_code:
        caption = f"🔥 PROMO CODE: {promo_code}\n\n" + caption
    
    try:
        media = []
        for i, img_url in enumerate(deal['image_list']):
            item = {"type": "photo", "media": img_url}
            if i == 0: item["caption"] = caption
            media.append(item)
        
        res = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMediaGroup", 
                            data={"chat_id": TG_CHAT_ID, "media": json.dumps(media)}).json()
        if res.get("ok"):
            print("✅ Posted to Telegram!")
            return True
    except Exception as e:
        print(f"❌ TG Error: {e}")
    return False

def log_to_supabase(status, deals_found, error=None):
    try:
        supabase.table("shadow_bot_logs").insert({
            "status": status,
            "deals_found": deals_found,
            "error_message": str(error) if error else None
        }).execute()
        print("📊 Logged run status to Supabase.")
    except Exception as e:
        print(f"⚠️ Failed to log to Supabase: {e}")

def run_shadow_bot():
    print("🕵️‍♂️ Shadow Bot starting (Desktop Stealth Mode)...")
    found_count = 0
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        else:
            history = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()
            
            print(f"🌐 Visiting Ella's Page (Desktop)...")
            page.goto(TARGET_PAGE_URL, timeout=60000, wait_until="domcontentloaded")
            time.sleep(10) # Give more time for load
            
            # Try to dismiss login modal if it exists
            try:
                page.keyboard.press("Escape")
                time.sleep(1)
                close_selectors = [
                    'div[aria-label="Close"]',
                    'div[aria-label="Dismiss"]',
                    'div[role="button"]:has-text("Not now")'
                ]
                for selector in close_selectors:
                    if page.locator(selector).is_visible():
                        print(f"✅ Dismissing login modal: {selector}")
                        page.locator(selector).click()
                        time.sleep(2)
                        break
            except Exception as e:
                print(f"⚠️ Modal dismissal failed (maybe none): {e}")

            # Scroll to load posts iteratively (Facebook mobile needs slow scrolling)
            print("🖱️ Scrolling deeper to load content...")
            for scroll in range(4):
                page.evaluate(f"window.scrollBy(0, 1000)")
                time.sleep(3)
            
            # Click all "See more" buttons to reveal full post content
            print("🔍 Revealing hidden content (See more)...")
            try:
                # Use a more specific selector for "See more" to avoid clicking other things
                # and use force=True to bypass potential interceptions
                see_more_buttons = page.locator("text='See more'")
                btn_count = see_more_buttons.count()
                for i in range(min(btn_count, 15)): 
                    btn = see_more_buttons.nth(i)
                    if btn.is_visible():
                        # Scroll to element first to avoid floating headers
                        btn.scroll_into_view_if_needed()
                        btn.click(force=True, timeout=2000)
                        time.sleep(0.5)
            except Exception as e:
                print(f"⚠️ Error clicking See more: {e}")

            deals_to_process = []
            
            print("🔗 Inspecting DOM anchor tags for hidden links and post text...")
            try:
                all_anchors = page.locator('a').all()
                for a in all_anchors:
                    href = a.get_attribute('href')
                    if not href: continue
                    
                    decoded_url = href
                    # If it's a Facebook external redirect link
                    if '/l.php?u=' in href:
                        try:
                            encoded_url = href.split('/l.php?u=')[1].split('&')[0]
                            import urllib.parse
                            decoded_url = urllib.parse.unquote(encoded_url)
                        except:
                            pass
                            
                    # Check if it's one of our target affiliate domains
                    if any(domain in decoded_url for domain in ['joylink.io', 'mavely.app.link', 'amzn.to', 'amazon.com/dp', 'amazon.com/gp/product']):
                        post_text = ""
                        try:
                            # Find the closest post container to extract text ONLY for this specific deal
                            post_container = a.evaluate_handle("el => el.closest('[role=\"article\"]') || document.body")
                            post_text = post_container.evaluate("el => el.innerText")
                        except:
                            post_text = page.evaluate("document.body.innerText")
                            
                        if not any(d['url'] == decoded_url for d in deals_to_process):
                            deals_to_process.append({"url": decoded_url, "text": post_text})
                            
            except Exception as e:
                print(f"⚠️ Error inspecting anchors: {e}")

            print(f"✅ Total unique affiliate URLs found: {len(deals_to_process)}")
            
            for deal_data in deals_to_process:
                target_link = deal_data['url']
                post_text = deal_data['text']
                
                try:
                    # Prevent duplicates via local history cache
                    if target_link in history:
                        print(f"⏩ Already processed link {target_link} (local cache). Skipping.")
                        continue
                    
                    # Resolve ASIN first to check against Supabase database
                    asin = resolve_asin(target_link)
                    if not asin:
                        continue

                    # Prevent duplicates via Supabase (ensures safety in ephemeral cloud servers)
                    if supabase:
                        res = supabase.table("deals_queue").select("id").eq("asin", asin).eq("platform", "shadow_bot").execute()
                        if res.data:
                            print(f"⏩ Already processed ASIN {asin} (Supabase). Skipping.")
                            # Sync local history cache
                            if target_link not in history:
                                history.append(target_link)
                                with open(HISTORY_FILE, "w") as f:
                                    json.dump(history[-200:], f)
                            continue

                    print(f"✨ Found New Deal! Link: {target_link} (ASIN: {asin})")
                    
                    # Search specifically for CODE in the exact post text!
                    promo_code = None
                    try:
                        patterns = [
                            r'(?:CODE|C0DE|PROMO|PROM0)[-:\s]+([A-Z0-9]{4,15})',
                            r'(?:OFF|0FF)[-:\s]+([A-Z0-9]{4,15})',
                            r'([A-Z0-9]{4,15})\s+(?:OFF|0FF)'
                        ]
                        
                        for pattern in patterns:
                            matches = re.findall(pattern, post_text, re.IGNORECASE)
                            for match in matches:
                                candidate = match.upper()
                                # Ignore common words that look like codes
                                if candidate not in ["DOCTYPE", "FACEBOOK", "AMAZON", "GOOGLE", "IPHONE", "SEE", "MORE"]:
                                    promo_code = candidate
                                    break
                            if promo_code:
                                break
                    except Exception as e:
                        print(f"⚠️ Error parsing promo code: {e}")
                    
                    if promo_code:
                        print(f"🏷️ Found Promo Code: {promo_code}")

                    deal = get_product_details(asin)
                    if deal:
                        deal['promo_code'] = promo_code
                        
                        # Post to all platforms
                        print(f"🚀 Blasting deal {asin} to social media...")
                        success = False
                        if post_to_facebook(deal, promo_code): success = True
                        #if post_to_instagram(deal, promo_code): success = True
                        if post_to_telegram(deal, promo_code): success = True
                        
                        if success:
                            found_count += 1
                            history.append(target_link)
                            with open(HISTORY_FILE, "w") as f:
                                json.dump(history[-200:], f) # Keep last 200
                            
                            # Log to deals_queue in Supabase as 'shadow_bot' to permanently remember
                            if supabase:
                                try:
                                    supabase.table("deals_queue").upsert({
                                        "asin": asin,
                                        "platform": "shadow_bot",
                                        "status": "posted",
                                        "title": deal.get("title"),
                                        "price": deal.get("price"),
                                        "image_url": deal.get("image_list")[0] if deal.get("image_list") else None,
                                        "affiliate_url": target_link,
                                        "rating": deal.get("rating"),
                                        "reviews_count": deal.get("reviews_count"),
                                        "promo_code": promo_code
                                    }).execute()
                                    print("💾 Saved shadow-posted deal details to Supabase.")
                                except Exception as dberr:
                                    print(f"⚠️ Supabase save warning: {dberr}")
                                    
                            print(f"✅ Successfully shadow-posted: {asin}")
                            # Give a little pause between posts if there are many
                            time.sleep(10)
                                    
                except Exception as e:
                    print(f"⚠️ Error processing deal: {e}")
                    
            browser.close()
            log_to_supabase("success", found_count)
    except Exception as e:
        print(f"❌ Shadow Bot Critical Error: {e}")
        log_to_supabase("error", found_count, error=e)

if __name__ == "__main__":
    run_shadow_bot()
