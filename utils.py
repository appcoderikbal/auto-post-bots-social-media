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
            # NOTE: media (image URLs) and ratings intentionally NOT stored in Supabase
            "affiliate_url": product_data.get("affiliate_url"),
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
                # NOTE: media (image URLs) and ratings intentionally NOT stored in Supabase
                "affiliate_url": product_data.get("affiliate_url"),
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
            f"💰 Extra savings! Enter {deal.get('promo_code')} at checkout!",
            f"🔥 Big markdown! Apply code {deal.get('promo_code')} to save more!",
            f"⚡ Limited-time code {deal.get('promo_code')} — while it lasts!",
            f"🎁 Bonus savings! Code {deal.get('promo_code')} lowers the price!",
            f"😱 Great value with code: {deal.get('promo_code')}",
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
            "Restock your home essentials! 📦",
            "An interior-designer favorite. 🤫",
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
            "Your new favorite outfit just arrived. 🛍️",
            "Skin care routine? UPGRADED. 🧴",
            "The glow-up is real. 🌟",
            "Walk like the world is your runway. 💃",
            "Adding to cart in 3... 2... 1... 🛒",
            "POV: You found the perfect fit on Amazon. 📸",
            "This one just hits different. 🔥"
        ],
        "savings": [
            "Stop overpaying! Check the price now. 🦆",
            "This deal is seriously good... 🤫",
            "My jaw dropped when I saw this. 📉",
            "Such a good find — grab it while it lasts! 🏃‍♂️",
            "A great time to buy. Seriously. 🗓️",
            "Your wallet's new best friend. 💰",
            "Save more than you spend. That's the goal. ✅",
            "You're going to want to check this one out. 👀",
            "This one is hard to ignore. 🤩",
            "Deals like this don't stick around long. ⌛"
        ],
        "generic": [
            "TikTok made me buy it and I have zero regrets. 🎥",
            "The hidden gem of Amazon. 💎",
            "Don't say I didn't warn you when it sells out. ⚠️",
            "Everyone is obsessed with this right now. 😍",
            "The gift that keeps on giving. 🎁",
            "Adding this to my wishlist immediately. ✨",
            "One for you, one for your bestie. 👯‍♀️",
            "This one is worth every penny. 🙌",
            "Thousands of happy buyers can't be wrong. 🌟",
            "Honestly didn't expect it to be this good. 😮"
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

    # 3. ASIN — used by post_to_fb.py to build the link comment (not in caption)

    # 4. Randomized SEO Tags (Exactly 5)
    seo_tags_list = [
        "#amazonfinds", "#amazondeals", "#bestamazonproducts", "#amazoninfluencer",
        "#tiktokmademebuyit", "#shoppinghaul", "#discountdeals", "#smartshopping",
        "#lifestylehacks", "#techdeals", "#homedecorideas", "#giftideas2026",
        "#amazonmusthaves", "#viralfinds", "#dealsonline", "#budgetfriendly",
        "#smartshopper", "#neverpayfullprice", "#hotdeals", "#dailydeals",
        "#shoppingaddict", "#instadeals", "#savebig",
        "#tiktokmademebuythis", "#amazonmademebuythis", "#viralus", "#usdeals",
        "#viralusa", "#usa"
    ]
    random.shuffle(seo_tags_list)
    seo_tags = " ".join(seo_tags_list[:5])

    # 5. Dynamic Content Shuffling
    # NOTE: Price, discount %, and review counts are intentionally excluded.
    # Amazon Associates policy prohibits displaying prices (they change in real-time)
    # and implies you cannot reproduce review counts or star ratings from Amazon.
    content_blocks = [
        f"{ep['box']} {deal['title']}\n\n",
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

    # Required Amazon Associates disclosure
    disclosure = "As an Amazon Associate we earn from qualifying purchases."

    if platform == "ig":
        # IG: no clickable links allowed in captions — direct to bio
        caption = (f"{random.choice(final_hooks)}\n\n"
                   f"{main_body}"
                   f"🔗 Link in bio \u2192 grab the deal!\n\n"
                   f"🔔 Follow @SnagPopOfficial so you never miss a deal!\n\n"
                   f"{disclosure}\n\n"
                   f"{seo_tags}")
    else:
        # FB: no link in caption — link is added as a comment after posting
        caption = (f"{random.choice(final_hooks)}\n\n"
                   f"{main_body}"
                   f"🛒 Deal link in the comments below \u2193\n\n"
                   f"🔔 Follow @SnagPopOfficial for daily deals!\n\n"
                   f"{disclosure}\n\n"
                   f"{seo_tags}")

    return caption
