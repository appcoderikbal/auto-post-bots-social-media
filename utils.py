import os
import random
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# Supabase Config
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def is_posted(asin, platform):
    """Checks Supabase to see if an ASIN has already been posted to a platform."""
    if not supabase: return False
    res = supabase.table("deals_queue").select("id").eq("asin", asin).eq("platform", platform).eq("status", "posted").execute()
    return len(res.data) > 0

def mark_posted(asin, platform, product_data=None):
    """Updates Supabase status to 'posted' and saves product details for the website."""
    if not supabase: return
    from datetime import datetime
    data = {
        "status": "posted",
        "created_at": datetime.now().isoformat()
    }
    if product_data:
        data.update({
            "title": product_data.get("title"),
            "price": product_data.get("price"),
            "old_price": product_data.get("old_price"),
            "discount": product_data.get("discount"),
            "image_url": product_data.get("image_list")[0] if product_data.get("image_list") else None,
            "affiliate_url": product_data.get("affiliate_url"),
            "rating": product_data.get("rating"),
            "reviews_count": product_data.get("reviews_count")
        })
    supabase.table("deals_queue").update(data).eq("asin", asin).eq("platform", platform).execute()

def mark_failed(asin, platform):
    """Updates Supabase status to 'failed' for a specific deal."""
    if not supabase: return
    supabase.table("deals_queue").update({"status": "failed"}).eq("asin", asin).eq("platform", platform).execute()

def add_to_queue(asin, platform, category=None, product_data=None):
    """Adds a new pending deal to the Supabase queue with full details if available."""
    if not supabase: return
    try:
        data = {
            "asin": asin, 
            "platform": platform, 
            "status": "pending",
            "category": category
        }
        if product_data:
            data.update({
                "title": product_data.get("title"),
                "price": product_data.get("price"),
                "old_price": product_data.get("old_price"),
                "discount": product_data.get("discount"),
                "image_url": product_data.get("image_url") if product_data.get("image_url") else (product_data.get("image_list")[0] if product_data.get("image_list") else None),
                "affiliate_url": product_data.get("affiliate_url"),
                "rating": product_data.get("rating"),
                "reviews_count": product_data.get("reviews_count"),
                "promo_code": product_data.get("promo_code")
            })
        supabase.table("deals_queue").upsert(data).execute()
    except Exception as e:
        print(f"⚠️ Could not add {asin} to {platform} queue: {e}")

def get_next_deal(platform):
    """Pulls the next 'pending' deal from Supabase for a specific platform."""
    if not supabase: 
        print("❌ Supabase client not initialized!")
        return None
    try:
        res = supabase.table("deals_queue").select("*").eq("platform", platform).eq("status", "pending").order("created_at").limit(1).execute()
        if res.data:
            return res.data[0]
        else:
            print(f"ℹ️ No pending deals found for {platform} in Supabase.")
    except Exception as e:
        print(f"❌ Supabase Error in get_next_deal: {e}")
    return None

def get_deal_caption(deal, platform="fb"):
    # 1. Extensive Hook Categories (50+ Hooks)
    title_lower = deal.get('title', '').lower()
    
    categories = {
        "promo": [
            f"🚨 PROMO CODE ALERT! Use code: {deal.get('promo_code')} 🚨",
            f"💰 MONEY GLITCH? Enter {deal.get('promo_code')} at checkout!",
            f"🔥 MISTAKE PRICE! Apply code {deal.get('promo_code')} to save BIG!",
            f"⚡ QUICK! Code {deal.get('promo_code')} expires SOON!",
            f"🎁 FREEBIE VIBES! Code {deal.get('promo_code')} drops the price!",
            f"😱 Amazon is practically giving this away with code: {deal.get('promo_code')}",
            f"🎫 UNLOCK SAVINGS: Use code {deal.get('promo_code')} now!",
            f"💸 Your bank account will thank you. Code: {deal.get('promo_code')}"
        ],
        "tech": [
            "Your setup is about to get a MAJOR upgrade. ⚡",
            "The gadget you didn't know you needed... until now. 📱",
            "Early adopters, REJOICE! This price is insane. 🚀",
            "Tech heaven just got a little cheaper. 💻",
            "Is this the best Amazon find of 2026? 🤯",
            "Upgrade your life without breaking the bank. 🛠️",
            "POV: You just found the ultimate tech deal. 🎥",
            "Future-proof your home with this steal. 🏠",
            "Don't buy the expensive version. Buy THIS. 🤫",
            "The reviews don't lie. This thing is a beast. 💪"
        ],
        "home": [
            "Your home called. It wants this. 🏠",
            "The ultimate life hack for your kitchen. 🍳",
            "Cleaning just got a lot more satisfying. ✨",
            "Restock your home for under $25! 📦",
            "Interior designers don't want you to know about this. 🤫",
            "Turn your house into a luxury oasis. 🌿",
            "The one thing your guest room is missing. 🛏️",
            "Dinner time just got 10x easier. 🥘",
            "Small upgrade, HUGE difference. ✅",
            "Host like a pro with this Amazon find. 🥂"
        ],
        "fashion": [
            "Main character energy starts here. ✨",
            "The 'it' item everyone is talking about. 👗",
            "Luxury vibes on a budget. 💅",
            "Get the look for 70% less. 👠",
            "Your new favorite outfit just arrived. 🛍️",
            "Skin care routine? UPGRADED. 🧴",
            "The glow-up is real. 🌟",
            "Walk like the world is your runway. 💃",
            "Adding to cart in 3... 2... 1... 🛒",
            "POV: You found the perfect fit on Amazon. 📸"
        ],
        "savings": [
            "I'm actually screaming at this price drop. 😱",
            "Stop overpaying! Duck the price now. 🦆",
            "This deal is literally illegal... 🤫",
            "My jaw dropped when I saw the discount. 📉",
            "Is this a pricing error? Grab it FAST! 🏃‍♂️",
            "Better than Black Friday deals. Seriously. 🗓️",
            "Your wallet's new best friend. 💰",
            "Save more than you spend. That's the goal. ✅",
            "Lowest price in 30 days! Don't miss out. ⏰",
            "I've never seen it this cheap before. EVER. 🚫"
        ],
        "generic": [
            "TikTok made me buy it, but the price made me LOVE it. 🎥",
            "The hidden gem of Amazon. 💎",
            "Don't say I didn't warn you when it sells out. ⚠️",
            "Everyone is obsessed with this right now. 😍",
            "The gift that keeps on giving. 🎁",
            "Adding this to my wishlist immediately. ✨",
            "One for you, one for your bestie. 👯‍♀️",
            "Wait until the end to see the price... 🫢",
            "The reviews are 5-star for a reason. ⭐",
            "Best $20 I ever spent. No cap. 🧢"
        ]
    }

    # Determine Category
    selected_hooks = categories["generic"]
    
    if deal.get('promo_code'):
        selected_hooks = categories["promo"]
    elif any(word in title_lower for word in ["smart", "phone", "laptop", "wireless", "headphones", "gaming", "pc", "tech", "electronic", "charging"]):
        selected_hooks = categories["tech"]
    elif any(word in title_lower for word in ["kitchen", "home", "vacuum", "blender", "air fryer", "bedroom", "decor", "cleaning", "tool", "organizer"]):
        selected_hooks = categories["home"]
    elif any(word in title_lower for word in ["skin", "hair", "dress", "shirt", "shoes", "watch", "makeup", "serum", "cream", "jewelry", "beauty"]):
        selected_hooks = categories["fashion"]
    elif any(word in str(deal.get('discount', '')).lower() for word in ["70", "80", "90", "off"]):
        selected_hooks = categories["savings"]

    # Combine with generic for variety
    final_hooks = selected_hooks + categories["generic"]
    
    # 2. Emojis & Parts
    ep = {"box": "📦", "money": "💰", "cart": "🛒", "tag": "🏷️", "star": "🌟", "fire": "🔥", "check": "✅"}
    rating = f"{ep['star']} Rating: {deal['rating']} {'⭐' * int(float(deal['rating']))} ({deal['reviews_count']} reviews)\n\n" if deal.get('rating') else ""
    
    # 3. Call to Action logic
    website_url = "https://www.snagpop.com"
    tracker_url = f"{website_url}/l/{deal['asin']}?s={platform}"
    
    url_text = ""
    fb_promo = "https://www.facebook.com/snagpopofficial"
    ig_promo = "https://www.instagram.com/snagpopofficial"
    
    if platform == "ig":
        cta = "link in bio -> all deals\n\n"
        url_text = ""
    elif platform == "tg":
        # Keep TG logic just in case, but it won't be called if removed from post_deals
        cta = f"🛒 Grab it here: "
        url_text = f"{tracker_url}\n\n📱 Follow us on Facebook: {fb_promo}"
    else: # fb
        cta = f"🛒 Grab it here: {tracker_url}\n\n"
        url_text = ""

    # 4. Randomized SEO Tags (Exactly 5)
    seo_tags_list = [
        "#amazonfinds", "#amazondeals", "#bestamazonproducts", "#amazoninfluencer", 
        "#tiktokmademebuyit", "#shoppinghaul", "#discountdeals", "#smartshopping",
        "#lifestylehacks", "#techdeals", "#homedecorideas", "#giftideas2026",
        "#amazonmusthaves", "#viralfinds", "#dealsonline", "#budgetfriendly",
        "#smartshopper", "#neverpayfullprice", "#hotdeals", "#dailydeals",
        "#shoppingaddict", "#instadeals", "#savebig"
    ]
    random.shuffle(seo_tags_list)
    seo_tags = " ".join(seo_tags_list[:5])

    # 5. Dynamic Content Shuffling
    content_blocks = [
        f"{ep['box']} {deal['title']}\n\n",
        f"{rating}",
        f"{ep['money']} Price: {deal['price']}{deal['discount_text']}\n\n"
    ]
    if deal.get('promo_code'):
        content_blocks.append(f"🎫 PROMO CODE: {deal['promo_code']} (Apply at checkout)\n\n")

    # Social Media Links
    fb_link = "https://facebook.com/snagpopofficial"
    ig_link = "https://instagram.com/snagpopofficial"
    yt_link = "https://youtube.com/@snagpopofficial"
    
    social_footer = (
        f"🔗 JOIN US FOR MORE:\n"
        f"👥 Facebook: {fb_link}\n"
        f"📸 Instagram: {ig_link}\n"
        f"🎥 YouTube: {yt_link}\n"
    )

    random.shuffle(content_blocks)
    main_body = "".join(content_blocks)

    if platform == "ig":
        caption = (f"link in bio -> all deals\n\n"
                   f"{random.choice(final_hooks)}\n\n"
                   f"{main_body}"
                   f"link in bio -> all deals\n\n"
                   f"🔔 Follow @SnagPopOfficial for daily glitch deals!\n\n"
                   f"{seo_tags}")
    else:
        caption = (f"{random.choice(final_hooks)}\n\n"
                   f"{main_body}"
                   f"🛒 GRAB IT HERE: {tracker_url}\n\n"
                   f"{social_footer}\n"
                   f"🔔 Follow @SnagPopOfficial for daily glitch deals!\n\n"
                   f"{seo_tags}")
    
    return caption
