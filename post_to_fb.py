import requests
import json
import sys
import os
from dotenv import load_dotenv
from utils import get_next_deal, mark_posted, mark_failed, get_deal_caption
from amazon_client import get_item

# Load environment variables
load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

# Config
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "100357853091828")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
# Facebook Place ID for location tagging (default: New York, United States)
FB_LOCATION_ID = os.getenv("FB_LOCATION_ID", "110843418940484")

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
            # Add a link comment on the post
            # NOTE: Facebook Graph API does NOT support pinning comments on Page posts
            # via API (is_pinned field is read-only). The link is already in the caption.
            website_url = "https://www.snagpop.com"
            tracker_url = f"{website_url}/l/{deal['asin']}?s=fb"
            fb_link = "https://www.facebook.com/snagpopofficial"
            try:
                comment_res = requests.post(
                    f"https://graph.facebook.com/v19.0/{result['id']}/comments",
                    data={
                        'message': f"🛒 Grab it here: {tracker_url}\n\n📢 Follow us for more deals: {fb_link}",
                        'access_token': FB_PAGE_ACCESS_TOKEN
                    }
                ).json()
                if 'id' in comment_res:
                    print(f"💬 Deal link comment added! ID: {comment_res['id']}")
                else:
                    print(f"⚠️ Comment failed: {comment_res}")
            except Exception as e:
                print(f"⚠️ Could not add link comment: {e}")
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
        deal = get_item(target_asin)
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
