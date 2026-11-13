"""
social_hooks.py — Opening lines for Facebook / Instagram posts.

60 hooks total, bucketed by product type. `pick_hook` builds a pool from the
deal's category, drops anything used in the last N posts (read from the
social_posted table), and picks at random from what's left — so the same
opener does not come back around for a long while.
"""

import random

KITCHEN_HOOKS = [
    "The ultimate life hack for your kitchen. 🍳",
    "Dinner time just got 10x easier. 🥘",
    "Every home cook needs this on the counter. 👩‍🍳",
    "Your kitchen drawer is about to get a serious upgrade. 🔪",
    "Meal prep Sunday just got a whole lot shorter. ⏱️",
    "The gadget that quietly replaced three others in my kitchen. ✨",
    "Host like a pro with this Amazon find. 🥂",
    "Why did nobody tell me about this sooner?! 🍽️",
    "Cooking is about to become your favourite part of the day. 🔥",
    "This is the one thing missing from your countertop. 🧈",
    "Restaurant-quality results, zero chef training required. 👨‍🍳",
    "The kitchen tool that's always, always in the sink — because it's always in use. 🧽",
    "Small gadget. Massive difference at dinner. 🍝",
    "Coffee lovers, this one is for you. ☕",
    "Baking season just got a serious assist. 🧁",
]

TECH_HOOKS = [
    "Your setup is about to get a MAJOR upgrade. ⚡",
    "The gadget you didn't know you needed... until now. 📱",
    "Early adopters, REJOICE! This price is wild. 🚀",
    "Tech heaven just got a little more affordable. 💻",
    "Don't buy the expensive version. Buy THIS. 🤫",
    "The reviews don't lie — this thing is a beast. 💪",
    "Future-proof your home with this one. 🏠",
    "Upgrade your life without wrecking your budget. 🛠️",
]

HOME_HOOKS = [
    "Your home called. It wants this. 🏠",
    "Cleaning just got weirdly satisfying. ✨",
    "An interior-designer favourite, quietly. 🤫",
    "Turn your place into a little luxury oasis. 🌿",
    "The one thing your guest room is missing. 🛏️",
    "Small upgrade, HUGE difference. ✅",
    "This is the cosy-home energy you've been after. 🕯️",
]

GENERAL_HOOKS = [
    "The hidden gem of Amazon. 💎",
    "Don't say I didn't warn you when it sells out. ⚠️",
    "Everyone is obsessed with this right now. 😍",
    "The gift that keeps on giving. 🎁",
    "Adding this to my cart immediately. ✨",
    "One for you, one for your bestie. 👯",
    "Worth every single penny. 🙌",
    "Thousands of happy buyers can't all be wrong. 🌟",
    "Honestly didn't expect it to be this good. 😮",
    "TikTok made me buy it and I have zero regrets. 🎥",
    "Stop overpaying — go check this one. 🦆",
    "This deal is seriously, seriously good. 🤫",
    "My jaw actually dropped. 📉",
    "Grab it while it lasts! 🏃",
    "Your wallet's new best friend. 💰",
    "You're going to want to see this one. 👀",
    "This one is hard to ignore. 🤩",
    "Deals like this don't hang around. ⌛",
    "Okay, this is a genuinely great find. 🏆",
    "I've been looking for something like this for months. 🔎",
    "Treat yourself. You've earned it. 💝",
    "This is your sign to finally get one. 🪧",
    "Quietly one of the best things on Amazon. 🤐",
    "The reviews on this one are unreal. ⭐",
    "File this one under 'why didn't I buy it sooner'. 🗂️",
]

PROMO_HOOKS = [
    "🚨 PROMO CODE ALERT — check the comments! 🚨",
    "💰 There's an extra code on this one. Don't miss it!",
    "🎫 UNLOCK EXTRA SAVINGS on this find!",
    "⚡ Limited-time code attached — while it lasts!",
    "🎁 Bonus savings stacked on top of this price!",
]

ALL_HOOKS = KITCHEN_HOOKS + TECH_HOOKS + HOME_HOOKS + GENERAL_HOOKS + PROMO_HOOKS

KITCHEN_WORDS = [
    "kitchen", "cookware", "cook", "blender", "air fryer", "airfryer", "knife",
    "knives", "pan", "pot", "skillet", "utensil", "mug", "coffee", "espresso",
    "baking", "bakeware", "cutting board", "spatula", "food storage", "container",
    "dish", "mixer", "kettle", "toaster", "grill", "strainer", "colander",
    "measuring", "peeler", "whisk", "tumbler", "chopper", "slicer",
]
TECH_WORDS = [
    "smart", "phone", "laptop", "wireless", "headphone", "earbud", "gaming",
    "pc", "tech", "electronic", "charging", "charger", "bluetooth", "monitor",
    "speaker", "camera", "tablet", "usb", "led",
]
HOME_WORDS = [
    "home", "decor", "vacuum", "bedroom", "cleaning", "organizer", "storage",
    "lamp", "rug", "curtain", "pillow", "blanket", "candle", "shelf", "bathroom",
    "furniture", "wall art",
]


def classify(deal: dict) -> str:
    """Bucket a deal into kitchen / tech / home / general from its title + category."""
    text = f"{deal.get('title') or ''} {deal.get('category') or ''}".lower()
    if any(w in text for w in KITCHEN_WORDS):
        return "kitchen"
    if any(w in text for w in TECH_WORDS):
        return "tech"
    if any(w in text for w in HOME_WORDS):
        return "home"
    return "general"


def is_kitchen(deal: dict) -> bool:
    """True if this deal reads as a kitchen product."""
    return classify(deal) == "kitchen"


def pick_hook(deal: dict, recent_hooks=None) -> str:
    """Choose an opening line suited to the deal, avoiding recently used ones."""
    recent = set(recent_hooks or [])

    if deal.get("promo_code"):
        pool = PROMO_HOOKS + GENERAL_HOOKS
    else:
        bucket = classify(deal)
        pool = {
            "kitchen": KITCHEN_HOOKS,
            "tech": TECH_HOOKS,
            "home": HOME_HOOKS,
            "general": [],
        }[bucket] + GENERAL_HOOKS

    fresh = [h for h in pool if h not in recent]
    if not fresh:
        # Everything in this bucket has been used lately — widen, then reset.
        fresh = [h for h in ALL_HOOKS if h not in recent] or pool
    return random.choice(fresh)
