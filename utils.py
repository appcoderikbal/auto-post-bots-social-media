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


# ── Telegram Queue (telegram_queue table — rows deleted after posting) ────────

def tg_add_to_queue(asin, platform, category=None, product_data=None):
    """Insert a deal into telegram_queue. Silently skips duplicates."""
    if not supabase:
        return
    try:
        data = {
            "asin": asin,
            "platform": platform,
            "category": category,
            "title": product_data.get("title") if product_data else None,
            "price": product_data.get("price") if product_data else None,
            "old_price": product_data.get("old_price") if product_data else None,
            "discount": product_data.get("discount") if product_data else None,
            "affiliate_url": product_data.get("affiliate_url") if product_data else None,
            "image_url": product_data.get("image_url") if product_data else None,
            "promo_code": product_data.get("promo_code") if product_data else None,
        }
        # upsert ignores duplicate (asin + platform) due to unique index
        supabase.table("telegram_queue").upsert(data, on_conflict="asin,platform").execute()
    except Exception as e:
        print(f"⚠️ Could not queue {asin} for {platform}: {e}")


def tg_get_mixed_deals(platform, count=4):
    """Pull up to `count` pending deals for a platform, mixed across different categories."""
    if not supabase:
        print("❌ Supabase client not initialized!")
        return []
    try:
        # Fetch the oldest 30 deals to have a pool to mix from
        res = (
            supabase.table("telegram_queue")
            .select("*")
            .eq("platform", platform)
            .order("created_at")
            .limit(30)
            .execute()
        )
        if not res.data:
            print(f"ℹ️ No deals queued for {platform}.")
            return []
            
        # Group by category to shuffle them
        deals_by_cat = {}
        for d in res.data:
            cat = d.get("category") or "Unknown"
            if cat not in deals_by_cat:
                deals_by_cat[cat] = []
            deals_by_cat[cat].append(d)
            
        selected = []
        cats = list(deals_by_cat.keys())
        random.shuffle(cats)
        
        # Round-robin selection to ensure category diversity
        while len(selected) < count and cats:
            for cat in list(cats):
                if deals_by_cat[cat]:
                    selected.append(deals_by_cat[cat].pop(0))
                    if len(selected) == count:
                        break
                else:
                    cats.remove(cat)
                    
        return selected
    except Exception as e:
        print(f"❌ Supabase error in tg_get_mixed_deals: {e}")
    return []


def tg_delete_deal(row_id):
    """Delete a deal row after it has been successfully posted."""
    if not supabase:
        return
    try:
        supabase.table("telegram_queue").delete().eq("id", row_id).execute()
    except Exception as e:
        print(f"⚠️ Could not delete deal row {row_id}: {e}")


def tg_is_queued(asin, platform):
    """Returns True if this ASIN is already in the queue for the platform."""
    if not supabase:
        return False
    res = (
        supabase.table("telegram_queue")
        .select("id")
        .eq("asin", asin)
        .eq("platform", platform)
        .execute()
    )
    return len(res.data) > 0


# ── Product Links (Website Redirection) ────────

def save_product_link(asin, region, affiliate_url, title=None):
    """Save the affiliate link so the website can look it up."""
    if not supabase: return
    if not affiliate_url: return
    try:
        data = {
            "asin": asin,
            "region": region,
            "affiliate_url": affiliate_url,
            "title": title
        }
        supabase.table("product_links").upsert(data, on_conflict="asin,region").execute()
    except Exception as e:
        print(f"⚠️ Could not save product link for {asin}: {e}")

def cleanup_old_product_links(days=3):
    """Delete product links older than `days`."""
    if not supabase: return
    try:
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        supabase.table("product_links").delete().lt("created_at", cutoff).execute()
        print(f"🧹 Cleaned up product links older than {days} days.")
    except Exception as e:
        print(f"⚠️ Error cleaning up product links: {e}")

def is_recently_processed(asin, region):
    """Returns True if the ASIN exists in product_links (meaning we fetched it in the last 3 days)."""
    if not supabase: return False
    res = supabase.table("product_links").select("id").eq("asin", asin).eq("region", region).execute()
    return len(res.data) > 0

def get_deal_caption(deal, platform="telegram"):
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

    random.shuffle(content_blocks)
    main_body = "".join(content_blocks)

    # Required Amazon Associates disclosure
    disclosure = "As an Amazon Associate we earn from qualifying purchases."

    # Telegram: link can be directly in caption
    link = f"https://www.snagpop.com/l/{deal['asin']}?s=tg"
    caption = (f"{random.choice(final_hooks)}\n\n"
               f"{main_body}"
               f"🛒 Get it here: {link}\n\n"
               f"🔔 Share with friends so they never miss a deal!\n\n"
               f"{disclosure}\n\n"
               f"{seo_tags}")

    return caption
