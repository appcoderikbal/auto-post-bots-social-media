"""
post_social.py — Posts the single best deal to Facebook and Instagram.

Runs 4x a day on US Eastern time (default 9 AM / 1 PM / 5 PM / 8 PM ET).
GitHub Actions cron is UTC and has no idea about DST, so the workflow fires
on every UTC hour that *could* be a slot and this script decides whether the
local ET hour is actually one — same self-skip pattern as run_bot.py.

Per platform it gathers candidates (the existing Telegram queue, read-only,
plus a live Amazon search), scores them, and posts the winner:

  Facebook  — product link AND the US Telegram invite in the post description.
  Instagram — NO link in the caption; the link goes in the first comment.
              Kitchen deals are strongly preferred here.

Every post is recorded in `social_posted` so a product never repeats, and the
hook is recorded too so the same opening line doesn't come back around.

Usage:
  python post_social.py                  # respects the ET schedule
  python post_social.py --force          # post right now, ignore the clock
  python post_social.py --dry-run        # pick + render captions, post nothing
  python post_social.py --platform ig    # one network only
"""

import os
import re
import sys
import json
import time
import random
import requests
from datetime import datetime
import pytz
from dotenv import load_dotenv

from amazon_client import search_deals, get_item
from social_hooks import pick_hook, is_kitchen
from utils import (
    tg_get_mixed_deals,
    social_is_posted,
    social_mark_posted,
    social_recent_hooks,
    cleanup_old_social_posts,
    get_social_caption,
    get_social_comment,
    save_product_link,
)

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

# ── Config ────────────────────────────────────────────────────────────────────

FB_PAGE_ID           = os.getenv("FB_PAGE_ID")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
IG_ACCOUNT_ID        = os.getenv("INSTAGRAM_ACCOUNT_ID")
# Facebook Place ID for location tagging (default: New York, United States)
FB_LOCATION_ID       = os.getenv("FB_LOCATION_ID", "110843418940484")
GRAPH                = "https://graph.facebook.com/v21.0"

TIMEZONE = os.getenv("SOCIAL_TIMEZONE", "America/New_York")
# 4 slots a day, US Eastern. Set to "9,14,19" for 3.
POST_HOURS = [int(h) for h in os.getenv("SOCIAL_POST_HOURS", "9,13,17,20").split(",") if h.strip()]

KITCHEN_SEARCHES = [
    {"query": "kitchen gadgets tools",        "index": "HomeAndKitchen"},
    {"query": "kitchen appliances useful",    "index": "HomeAndKitchen"},
    {"query": "cookware nonstick set",        "index": "HomeAndKitchen"},
    {"query": "coffee maker accessories",     "index": "HomeAndKitchen"},
    {"query": "food storage containers",      "index": "HomeAndKitchen"},
]

GENERAL_SEARCHES = [
    {"query": "home decor accessories",       "index": "HomeAndKitchen"},
    {"query": "kitchen gadgets tools",        "index": "HomeAndKitchen"},
    {"query": "tech gadgets electronics",     "index": "Electronics"},
    {"query": "smart home devices",           "index": "Electronics"},
    {"query": "kitchen appliances",           "index": "HomeAndKitchen"},
    {"query": "home decor living room",       "index": "HomeAndKitchen"},
]


# ── Identity ──────────────────────────────────────────────────────────────────

def identify_accounts():
    """Resolve and print exactly which Page / IG account we're about to post to.

    The IDs alone aren't much use in a run log, so ask the Graph API for the
    human-readable name and echo it before anything is published.
    """
    print("🔎 Resolving target accounts...")

    if FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN:
        try:
            res = requests.get(
                f"{GRAPH}/{FB_PAGE_ID}",
                params={"fields": "name,username,link",
                        "access_token": FB_PAGE_ACCESS_TOKEN},
                timeout=20,
            ).json()
            if "name" in res:
                print(f"  📘 Facebook Page : {res['name']}  (id {FB_PAGE_ID})")
                if res.get("link"):
                    print(f"                     {res['link']}")
            else:
                print(f"  ⚠️ Could not resolve FB page {FB_PAGE_ID}: "
                      f"{res.get('error', {}).get('message', res)}")
        except Exception as e:
            print(f"  ⚠️ FB identity lookup failed: {e}")
    else:
        print("  📘 Facebook: credentials not set.")

    if IG_ACCOUNT_ID and FB_PAGE_ACCESS_TOKEN:
        try:
            res = requests.get(
                f"{GRAPH}/{IG_ACCOUNT_ID}",
                params={"fields": "username,name,followers_count",
                        "access_token": FB_PAGE_ACCESS_TOKEN},
                timeout=20,
            ).json()
            if "username" in res:
                print(f"  📸 Instagram     : @{res['username']}  (id {IG_ACCOUNT_ID})")
                print(f"                     https://instagram.com/{res['username']}")
            else:
                print(f"  ⚠️ Could not resolve IG account {IG_ACCOUNT_ID}: "
                      f"{res.get('error', {}).get('message', res)}")
        except Exception as e:
            print(f"  ⚠️ IG identity lookup failed: {e}")
    else:
        print("  📸 Instagram: credentials not set.")


# ── Scheduling ────────────────────────────────────────────────────────────────

def current_slot():
    """Return the ET hour if now is a posting slot, else None."""
    now = datetime.now(pytz.timezone(TIMEZONE))
    hour = now.hour
    label = now.strftime("%a %H:%M %Z")
    if hour in POST_HOURS:
        print(f"🕐 {label} — ✅ posting slot (slots: {POST_HOURS})")
        return hour
    print(f"🕐 {label} — ⏭️ not a posting slot (slots: {POST_HOURS})")
    return None


# ── Deal selection ────────────────────────────────────────────────────────────

def _pct(value):
    """Parse '35%' / '35' into a float, or 0.0."""
    if not value:
        return 0.0
    m = re.search(r"(\d+(?:\.\d+)?)", str(value))
    return float(m.group(1)) if m else 0.0


def score_deal(deal):
    """Rank a deal: discount first, then social proof, then image count.

    Images matter because Instagram carousels need 2-10 of them, and a post
    with 5 photos simply performs better than one with a single thumbnail.
    """
    score  = _pct(deal.get("discount")) * 2.0
    score += float(deal.get("rating") or 0) * 4.0
    score += min(int(deal.get("reviews_count") or 0), 5000) / 250.0
    score += min(len(deal.get("image_list") or []), 5) * 2.0
    if deal.get("promo_code"):
        score += 10.0
    return round(score, 2)


def _normalize(row):
    """Coerce a telegram_queue row into the shape amazon_client returns."""
    images = row.get("image_list")
    if not images:
        images = [row["image_url"]] if row.get("image_url") else []
    return {
        "asin":          row.get("asin"),
        "title":         row.get("title"),
        "price":         row.get("price"),
        "discount":      row.get("discount"),
        "affiliate_url": row.get("affiliate_url"),
        "image_url":     row.get("image_url"),
        "image_list":    images,
        "rating":        row.get("rating"),
        "reviews_count": row.get("reviews_count"),
        "promo_code":    row.get("promo_code"),
        "category":      row.get("category"),
    }


def gather_candidates(platform, prefer_kitchen):
    """Collect deal candidates from the Telegram queue plus a live Amazon search."""
    pool, seen = [], set()

    def add(deal):
        asin = deal.get("asin")
        if not asin or asin in seen:
            return
        if not deal.get("title") or not deal.get("image_url"):
            return
        seen.add(asin)
        pool.append(deal)

    # 1. Reuse what's already queued for Telegram US. Read-only — the Telegram
    #    bot owns those rows and deletes them itself; we must not consume them.
    try:
        for row in tg_get_mixed_deals("telegram_us", count=30):
            add(_normalize(row))
    except Exception as e:
        print(f"⚠️ Could not read the Telegram queue: {e}")
    print(f"  📥 {len(pool)} candidate(s) from the existing queue.")

    # 2. Top up with a fresh Amazon search.
    searches = KITCHEN_SEARCHES if prefer_kitchen else GENERAL_SEARCHES
    for cat in random.sample(searches, min(2, len(searches))):
        try:
            found = search_deals(
                cat["query"],
                search_index=cat["index"],
                min_saving_percent=15,
                item_count=10,
                region="us",
            )
            for deal in found or []:
                add(deal)
        except Exception as e:
            print(f"⚠️ Amazon search failed for '{cat['query']}': {e}")
    print(f"  📥 {len(pool)} candidate(s) total after the live search.")

    # 3. Drop anything already posted on this network.
    fresh = [d for d in pool if not social_is_posted(d["asin"], platform)]
    print(f"  🔁 {len(pool) - len(fresh)} already posted to {platform.upper()}, "
          f"{len(fresh)} remain.")
    return fresh


def enrich_images(deal):
    """Fetch the product's full image set before posting.

    Deals sourced from a keyword search carry a single image: the Creators
    API search envelope and RapidAPI's /search both return one photo per hit
    (`product_photo`, singular). The per-product lookup returns the whole
    `product_photos` array, which is what a carousel needs — so spend one
    extra call on the single deal we're actually about to publish.
    """
    have = [i for i in (deal.get("image_list") or []) if i]
    if len(have) >= 2:
        print(f"  🖼️ {len(have)} image(s) already — no lookup needed.")
        return deal

    print(f"  🖼️ Only {len(have)} image — fetching the full set for {deal['asin']}...")
    try:
        full = get_item(deal["asin"], region="us")
    except Exception as e:
        print(f"  ⚠️ Image lookup failed: {e}")
        return deal

    if not full:
        print("  ⚠️ Product lookup returned nothing — posting with what we have.")
        return deal

    richer = [i for i in (full.get("image_list") or []) if i]
    if len(richer) > len(have):
        print(f"  ✅ Images: {len(have)} → {len(richer)}")
        deal["image_list"] = richer
        deal["image_url"] = richer[0]
        # The detail endpoint also carries better review data than search does.
        for field in ("rating", "reviews_count", "discount", "price"):
            if not deal.get(field) and full.get(field):
                deal[field] = full[field]
    else:
        print(f"  ℹ️ No extra images available (still {len(have)}).")
    return deal


def pick_best(platform):
    """Return the highest-scoring unposted deal for this platform, or None."""
    prefer_kitchen = platform == "ig"
    candidates = gather_candidates(platform, prefer_kitchen)
    if not candidates:
        return None

    if prefer_kitchen:
        kitchen = [d for d in candidates if is_kitchen(d)]
        if kitchen:
            print(f"  🍳 {len(kitchen)} kitchen deal(s) — Instagram picks from these.")
            candidates = kitchen
        else:
            print("  ⚠️ No kitchen deals available — falling back to the full pool.")

    best = max(candidates, key=score_deal)
    print(f"  🏆 Best: {best['title'][:60]}... "
          f"(score {score_deal(best)}, discount {best.get('discount') or 'n/a'}, "
          f"{len(best.get('image_list') or [])} image(s))")
    return best


# ── Facebook ──────────────────────────────────────────────────────────────────

def post_facebook(deal, hook, dry_run=False):
    """Post to the Page with the product link + Telegram invite in the body."""
    caption = get_social_caption(deal, "fb", hook)
    images  = [i for i in (deal.get("image_list") or [deal.get("image_url")]) if i][:10]

    if dry_run:
        print(f"\n--- FACEBOOK caption ({len(images)} image(s)) ---\n{caption}\n---")
        return "dry-run"

    if not (FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN):
        print("❌ FB_PAGE_ID / FB_PAGE_ACCESS_TOKEN missing — skipping Facebook.")
        return None

    try:
        # Upload each photo unpublished, then attach them all to one feed post.
        photo_ids = []
        for img in images:
            res = requests.post(
                f"{GRAPH}/{FB_PAGE_ID}/photos",
                data={"url": img, "published": "false",
                      "access_token": FB_PAGE_ACCESS_TOKEN},
                timeout=30,
            ).json()
            if "id" in res:
                photo_ids.append(res["id"])
            else:
                print(f"  ⚠️ Photo upload failed: {res.get('error', {}).get('message', res)}")

        if not photo_ids:
            print("❌ No photos uploaded — skipping Facebook.")
            return None

        payload = {
            "message": caption,
            "attached_media": json.dumps([{"media_fbid": p} for p in photo_ids]),
            "access_token": FB_PAGE_ACCESS_TOKEN,
        }
        if FB_LOCATION_ID:
            payload["place"] = FB_LOCATION_ID

        result = requests.post(f"{GRAPH}/{FB_PAGE_ID}/feed", data=payload, timeout=30).json()
        if "id" in result:
            print(f"✅ Posted to Facebook! ID: {result['id']}")
            return result["id"]
        print(f"❌ Facebook post failed: {result}")
    except Exception as e:
        print(f"❌ Error posting to Facebook: {e}")
    return None


# ── Instagram ─────────────────────────────────────────────────────────────────

def _ig_image(url):
    """Normalize an Amazon image URL to the full-size original.

    IG's media fetcher intermittently fails on Amazon's sized variants
    (e.g. '..._AC_SL1500_.jpg'). Stripping the size modifier yields the
    canonical image, which IG fetches reliably.
    """
    if not url:
        return url
    return re.sub(r"\._[^./]+_\.(jpg|jpeg|png)", r".\1", url, flags=re.IGNORECASE)


def _ig_container(**data):
    """Create a media container, retrying once on a transient fetch failure."""
    data["access_token"] = FB_PAGE_ACCESS_TOKEN
    for attempt in range(2):
        res = requests.post(f"{GRAPH}/{IG_ACCOUNT_ID}/media", data=data, timeout=30).json()
        if "id" in res:
            return res["id"]
        print(f"  ❌ IG container failed (attempt {attempt + 1}): "
              f"{res.get('error', {}).get('message', res)}")
        if attempt == 0:
            time.sleep(3)
    return None


def post_instagram(deal, hook, dry_run=False):
    """Post to Instagram with NO link in the caption, then comment the link."""
    caption = get_social_caption(deal, "ig", hook)
    comment = get_social_comment(deal, "ig")
    images  = [_ig_image(i) for i in (deal.get("image_list") or [deal.get("image_url")])[:10] if i]

    if dry_run:
        print(f"\n--- INSTAGRAM caption ({len(images)} image(s)) ---\n{caption}\n"
              f"--- first comment ---\n{comment}\n---")
        return "dry-run"

    if not (IG_ACCOUNT_ID and FB_PAGE_ACCESS_TOKEN):
        print("❌ INSTAGRAM_ACCOUNT_ID / FB_PAGE_ACCESS_TOKEN missing — skipping Instagram.")
        return None
    if not images:
        print("❌ No images for this deal — skipping Instagram.")
        return None

    try:
        if len(images) >= 2:
            # Carousel: one child container per image, then a parent.
            children = [cid for cid in
                        (_ig_container(image_url=i, is_carousel_item="true") for i in images)
                        if cid]
            if len(children) < 2:
                print(f"  ⚠️ Only {len(children)} image(s) usable — posting a single image.")
                creation_id = _ig_container(image_url=images[0], caption=caption,
                                            location_id=FB_LOCATION_ID)
            else:
                creation_id = _ig_container(caption=caption, media_type="CAROUSEL",
                                            children=",".join(children),
                                            location_id=FB_LOCATION_ID)
        else:
            creation_id = _ig_container(image_url=images[0], caption=caption,
                                        location_id=FB_LOCATION_ID)

        if not creation_id:
            print("❌ Could not create an IG container — skipping Instagram.")
            return None

        time.sleep(5)  # IG needs a moment to process the container before publish

        result = requests.post(
            f"{GRAPH}/{IG_ACCOUNT_ID}/media_publish",
            data={"creation_id": creation_id, "access_token": FB_PAGE_ACCESS_TOKEN},
            timeout=30,
        ).json()

        if "id" not in result:
            print(f"❌ IG publish failed: {result}")
            return None

        media_id = result["id"]
        print(f"✅ Posted to Instagram! ID: {media_id}")

        # The link lives here, not in the caption.
        time.sleep(2)
        c_res = requests.post(
            f"{GRAPH}/{media_id}/comments",
            data={"message": comment, "access_token": FB_PAGE_ACCESS_TOKEN},
            timeout=30,
        ).json()

        if "id" in c_res:
            print(f"💬 Link comment posted! ID: {c_res['id']}")
            # Instagram's Graph API exposes no pin/is_pinned field — only `hide`
            # is updatable on a comment. Being first it sits at the top anyway;
            # pin it in the app if you want it locked there.
            print("📌 Note: IG has no pin API — pin it manually in the app to lock it up top.")
        else:
            print(f"⚠️ Link comment failed: {c_res.get('error', {}).get('message', c_res)}")

        return media_id
    except Exception as e:
        print(f"❌ Error posting to Instagram: {e}")
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def run_platform(platform, recent_hooks, dry_run=False):
    print(f"\n{'─' * 60}")
    print(f"📣 {platform.upper()}")

    deal = pick_best(platform)
    if not deal:
        print(f"  ⚠️ No eligible deal for {platform.upper()} right now.")
        return None, None

    deal = enrich_images(deal)

    hook = pick_hook(deal, recent_hooks=recent_hooks)
    print(f"  🎣 Hook: {hook}")

    poster = post_facebook if platform == "fb" else post_instagram
    post_id = poster(deal, hook, dry_run=dry_run)

    if post_id and not dry_run:
        social_mark_posted(deal["asin"], platform, hook=hook, post_id=post_id,
                           title=deal.get("title"), score=score_deal(deal))
        # Keep the website redirect working for the link we just published.
        save_product_link(deal["asin"], "us", deal.get("affiliate_url"), deal.get("title"))
    return hook, (post_id, deal.get("title"))


def _env_flag(name):
    """Read a boolean-ish env var. GitHub passes literal 'true'/'false'."""
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def run():
    args    = sys.argv[1:]
    # CLI flags for local use; env vars so CI doesn't need YAML expression
    # gymnastics to build an argument string.
    force   = "--force" in args or _env_flag("SOCIAL_FORCE")
    dry_run = "--dry-run" in args or _env_flag("SOCIAL_DRY_RUN")

    platforms = ["fb", "ig"]
    requested = None
    if "--platform" in args:
        requested = args[args.index("--platform") + 1]
    elif os.getenv("SOCIAL_PLATFORM", "").strip():
        requested = os.getenv("SOCIAL_PLATFORM").strip()

    if requested and requested.lower() not in ("", "both", "all"):
        requested = requested.lower()
        if requested not in ("fb", "ig"):
            print(f"❌ Unknown platform '{requested}' — expected fb, ig, or both.")
            sys.exit(1)
        platforms = [requested]
    print(f"🎯 Target platform(s): {', '.join(p.upper() for p in platforms)}")

    if not force and not dry_run and current_slot() is None:
        print("✅ Nothing to do this hour.")
        return

    identify_accounts()

    if not dry_run:
        cleanup_old_social_posts(days=45)

    # Hooks used recently, so this run picks something different.
    recent = social_recent_hooks(limit=25)
    results = {}
    for platform in platforms:
        hook, posted = run_platform(platform, recent, dry_run=dry_run)
        if hook:
            recent.append(hook)   # don't reuse it on the next network either
        results[platform] = posted
        time.sleep(3)

    print(f"\n{'─' * 60}")
    print("📊 SUMMARY")
    for platform in platforms:
        posted = results.get(platform)
        if not posted or not posted[0]:
            print(f"  {platform.upper():3s} — ❌ nothing posted")
            continue
        post_id, title = posted
        print(f"  {platform.upper():3s} — ✅ {title[:50]}")
        print(f"        post id: {post_id}")
        if post_id != "dry-run":
            if platform == "fb":
                print(f"        https://facebook.com/{post_id}")
            else:
                print(f"        https://www.instagram.com/p/  (media id {post_id})")
    print("✅ Social run complete.")


if __name__ == "__main__":
    run()
