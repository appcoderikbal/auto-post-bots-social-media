import requests
import urllib.parse
import json
import sys
import os
import random
import time
from dotenv import load_dotenv
from utils import get_next_deal, mark_posted, mark_failed, get_deal_caption

# Load environment variables
load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

# Config
AMAZON_ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "dealducker09-20")
IG_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN") # Uses the same token
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

def post_instagram_carousel(deal):
    print(f"📤 Posting Carousel to Instagram: {deal['title'][:50]}...")
    caption = get_deal_caption(deal, platform="ig")
    
    try:
        if not IG_ACCOUNT_ID:
            print("❌ Instagram Account ID missing in .env")
            return False

        # Step 1: Create Item Containers for each image
        container_ids = []
        for img_url in deal['image_list']:
            res = requests.post(
                f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media",
                data={
                    'image_url': img_url,
                    'is_carousel_item': 'true',
                    'access_token': FB_PAGE_ACCESS_TOKEN
                }
            ).json()
            if 'id' in res:
                container_ids.append(res['id'])
            else:
                print(f"❌ Error creating IG item container: {res}")
        
        if not container_ids: return False

        # Step 2: Create Carousel Container
        res = requests.post(
            f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media",
            data={
                'caption': caption,
                'media_type': 'CAROUSEL',
                'children': ','.join(container_ids),
                'location_id': FB_LOCATION_ID,
                'access_token': FB_PAGE_ACCESS_TOKEN
            }
        ).json()
        
        if 'id' not in res:
            print(f"❌ Error creating IG carousel container: {res}")
            return False
        
        creation_id = res['id']

        # Step 3: Wait a bit for processing (IG requirement)
        time.sleep(5)

        # Step 4: Publish Carousel
        result = requests.post(
            f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media_publish",
            data={
                'creation_id': creation_id,
                'access_token': FB_PAGE_ACCESS_TOKEN
            }
        ).json()
        
        if 'id' in result:
            ig_media_id = result['id']
            print(f"✅ Posted Carousel to Instagram! ID: {ig_media_id}")
            
            # Add comment (No direct links for IG)
            try:
                comment_res = requests.post(
                    f"https://graph.facebook.com/v19.0/{ig_media_id}/comments",
                    data={
                        'message': "link in bio -> all deals",
                        'access_token': FB_PAGE_ACCESS_TOKEN
                    }
                ).json()
                if 'id' in comment_res:
                    print(f"💬 Added comment to Instagram! ID: {comment_res['id']}")
                else:
                    print(f"⚠️ Failed to add IG comment: {comment_res}")
            except Exception as e:
                print(f"⚠️ Error adding IG comment: {e}")
                
            return True
        else:
            print(f"❌ Error publishing to IG: {result}")
    except Exception as e:
        print(f"❌ Error posting to IG: {e}")
    return False

if __name__ == "__main__":
    while True:
        deal_record = get_next_deal("ig")
                
        if not deal_record:
            print("No new deals for Instagram in database.")
            break
            
        target_asin = deal_record['asin']
        deal = get_deal_data(target_asin)
        if deal:
            # Merge promo code from DB if exists
            deal['promo_code'] = deal_record.get('promo_code')
            
            if post_instagram_carousel(deal):
                mark_posted(target_asin, "ig", deal)
                break
            else:
                print(f"⚠️ IG Post failed for {target_asin}. Marking as failed and trying next...")
                mark_failed(target_asin, "ig")
        else:
            print(f"⚠️ Skipping {target_asin} (Not found on Amazon).")
            mark_failed(target_asin, "ig")
