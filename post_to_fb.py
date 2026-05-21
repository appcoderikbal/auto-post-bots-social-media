import requests
import urllib.parse
import json
import sys
import os
import random
from dotenv import load_dotenv
from utils import get_next_deal, mark_posted, mark_failed, get_deal_caption

# Load environment variables
load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

# Config
AMAZON_ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "dealducker09-20")
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "100357853091828")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "amazon-data-scraper-api3.p.rapidapi.com")
# Facebook Place ID for location tagging (default: New York, United States)
FB_LOCATION_ID = os.getenv("FB_LOCATION_ID", "110843418940484")

def get_deal_data(asin):
    print(f"🔍 Fetching product for ASIN: '{asin}'...")
    url = f"https://{RAPIDAPI_HOST}/queries"
    payload = {"source": "amazon_product", "query": asin, "geo_location": "90210", "parse": True}
    headers = {"content-type": "application/json", "X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST}
    try:
        response = requests.post(url, json=payload, headers=headers).json()
        content = response.get("results", [])[0].get("content", {})
        if not content: return None
        
        base_url = content.get("url", "")
        parsed_url = urllib.parse.urlparse(base_url)
        separator = '&' if parsed_url.query else '?'
        
        return {
            "asin": asin,
            "title": content.get("title", "Amazing Amazon Find!"),
            "price": f"${content.get('price')}" if content.get('price') else "Check link",
            "discount_text": f" ({content.get('discount_percentage')}% OFF!)" if content.get('discount_percentage') else "",
            "affiliate_url": f"{base_url}{separator}tag={AMAZON_ASSOCIATE_TAG}",
            "image_list": content.get("images", [])[:4],
            "rating": content.get("rating"),
            "reviews_count": content.get("reviews_count")
        }
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def post_carousel(deal):
    print(f"📤 Posting Carousel to Facebook: {deal['title'][:50]}...")
    message = get_deal_caption(deal, platform="fb")
    
    try:
        photo_ids = []
        for img_url in deal['image_list']:
            res = requests.post(f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos", data={'url': img_url, 'published': 'false', 'access_token': FB_PAGE_ACCESS_TOKEN}).json()
            if 'id' in res: photo_ids.append(res['id'])
        
        attached_media = json.dumps([{"media_fbid": pid} for pid in photo_ids])
        result = requests.post(f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed", data={'message': message, 'attached_media': attached_media, 'place': FB_LOCATION_ID, 'access_token': FB_PAGE_ACCESS_TOKEN}).json()
        
        if 'id' in result:
            print(f"✅ Posted Carousel to Facebook! ID: {result['id']}")
            # Add comment with link
            website_url = "https://www.snagpop.com"
            tracker_url = f"{website_url}/l/{deal['asin']}?s=fb"
            fb_link = "https://www.facebook.com/snagpopofficial"
            try:
                requests.post(
                    f"https://graph.facebook.com/v19.0/{result['id']}/comments",
                    data={
                        'message': f"🛒 Grab it here: {tracker_url}\n\n📢 Follow us on Facebook for more deals: {fb_link}",
                        'access_token': FB_PAGE_ACCESS_TOKEN
                    }
                )
            except Exception as e:
                print(f"⚠️ Could not post comment: {e}")
            return True
    except Exception as e:
        print(f"❌ Error posting to FB: {e}")
    return False

if __name__ == "__main__":
    while True:
        deal_record = get_next_deal("fb")
                
        if not deal_record:
            print("No new deals for Facebook in database.")
            break
            
        target_asin = deal_record['asin']
        deal = get_deal_data(target_asin)
        if deal:
            # Merge promo code from DB if exists
            deal['promo_code'] = deal_record.get('promo_code')
            
            if post_carousel(deal):
                mark_posted(target_asin, "fb", deal)
                break
            else:
                print(f"⚠️ FB Post failed for {target_asin}. Marking as failed and trying next...")
                mark_failed(target_asin, "fb")
        else:
            print(f"⚠️ Skipping {target_asin} (Not found on Amazon).")
            mark_failed(target_asin, "fb")
