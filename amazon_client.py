"""
Amazon Creators API client.

Single source of truth for all Amazon product data (title, price, discount,
images, ratings, affiliate links). Replaces the previous third-party RapidAPI
scraper so that data comes from Amazon's official, Associates-compliant API.

Auth: Login-with-Amazon OAuth2 (client_credentials). The client_id/secret are
exchanged for a 1-hour bearer token which is cached in-process.

Endpoints (REST, JSON, lowerCamelCase):
  POST {API_BASE}/catalog/v1/getItems
  POST {API_BASE}/catalog/v1/searchItems

Returns plain dicts shaped exactly like the rest of the codebase expects, so
callers (post_to_fb, post_to_ig, fetch_promo_deals, refresh_deals,
fb_shadow_bot) need no schema changes.

NOTE: Some field paths (savings/discount under offersV2, the searchItems
response envelope) are not fully documented publicly and are handled
defensively here. Verify them against a live response and adjust the
candidate paths in _map_item / search_deals if needed.
"""

import os
import time
import urllib.parse
import requests
from dotenv import load_dotenv

load_dotenv()

# --- Credentials & config (from Associates Central -> Creators API) ----------
CLIENT_ID = os.getenv("AMAZON_CREATORS_CLIENT_ID")
CLIENT_SECRET = os.getenv("AMAZON_CREATORS_CLIENT_SECRET")
PARTNER_TAG = os.getenv("AMAZON_CREATORS_PARTNER_TAG") or os.getenv("AMAZON_ASSOCIATE_TAG", "dealducker09-20")
MARKETPLACE = os.getenv("AMAZON_MARKETPLACE", "www.amazon.com")

# Overridable in case Amazon changes hosts/scopes.
TOKEN_URL = os.getenv("AMAZON_TOKEN_URL", "https://api.amazon.com/auth/o2/token")
API_BASE = os.getenv("AMAZON_CREATORS_API_BASE", "https://creatorsapi.amazon")
SCOPE = os.getenv("AMAZON_CREATORS_SCOPE", "creatorsapi::default")

# --- Temporary RapidAPI scraper fallback -------------------------------------
# Used only when the Creators API is unavailable (e.g. account not yet eligible
# for the Creators API). Remove once the Creators API is fully enabled.
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "amazon-data-scraper-api3.p.rapidapi.com")
FALLBACK_ENABLED = os.getenv("AMAZON_FALLBACK_ENABLED", "true").lower() == "true"

# Resources requested from the API (analogous to PA-API resources).
RESOURCES = [
    "itemInfo.title",
    "images.primary.large",
    "images.variants.large",
    "offersV2.listings.price",
    "customerReviews.starRating",
    "customerReviews.count",
]

_token = {"value": None, "expires_at": 0.0}


def _get_token():
    """Return a cached bearer token, refreshing via OAuth2 when expired."""
    now = time.time()
    if _token["value"] and now < _token["expires_at"] - 60:
        return _token["value"]
    if not (CLIENT_ID and CLIENT_SECRET):
        print("⚠️ Amazon Creators API credentials missing (AMAZON_CREATORS_CLIENT_ID / _SECRET).")
        return None
    try:
        res = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "scope": SCOPE,
            },
            timeout=15,
        ).json()
        token = res.get("access_token")
        if token:
            _token["value"] = token
            _token["expires_at"] = now + int(res.get("expires_in", 3600))
            return token
        print(f"❌ Token error: {res}")
    except Exception as e:
        print(f"❌ Token request failed: {e}")
    return None


def _headers():
    token = _get_token()
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "x-marketplace": MARKETPLACE,
    }


def _dig(obj, *path):
    """Safely walk nested dict keys / list indexes, returning None on any miss."""
    for p in path:
        if obj is None:
            return None
        if isinstance(p, int):
            try:
                obj = obj[p]
            except (IndexError, TypeError, KeyError):
                return None
        else:
            if isinstance(obj, dict):
                obj = obj.get(p)
            else:
                return None
    return obj


def _map_item(item):
    """Map a Creators API item object (dict) to the project's standard dict."""
    listing = _dig(item, "offersV2", "listings", 0)
    price_disp = _dig(listing, "price", "displayAmount")

    # Savings/discount path isn't fully documented; try the likely candidates.
    savings_pct = (
        _dig(listing, "price", "savings", "percentage")
        or _dig(listing, "price", "savingBasis", "savingsPercentage")
    )
    old_price_disp = (
        _dig(listing, "price", "savingBasis", "displayAmount")
        or _dig(listing, "price", "savingBasis", "money", "displayAmount")
    )

    # Collect official Amazon-hosted image URLs (primary first, then variants).
    images = []
    primary = _dig(item, "images", "primary", "large", "url")
    if primary:
        images.append(primary)
    for v in (_dig(item, "images", "variants") or []):
        url = _dig(v, "large", "url")
        if url:
            images.append(url)

    rating = _dig(item, "customerReviews", "starRating", "value") or _dig(item, "customerReviews", "starRating")
    reviews_count = _dig(item, "customerReviews", "count")

    return {
        "asin": _dig(item, "asin"),
        "title": _dig(item, "itemInfo", "title", "displayValue") or "Amazing Amazon Find!",
        "price": price_disp or "Check price",
        "old_price": old_price_disp,
        "discount": f"{savings_pct}%" if savings_pct else None,
        "discount_text": f" ({savings_pct}% OFF!)" if savings_pct else "",
        # detailPageURL is already tagged with the partner tag by the API.
        "affiliate_url": _dig(item, "detailPageURL"),
        "image_url": images[0] if images else None,
        "image_list": images[:5],
        "rating": rating,
        "reviews_count": reviews_count,
    }


def _post(path, body):
    """POST a JSON body to a Creators API endpoint; return parsed JSON or None."""
    headers = _headers()
    if not headers:
        return None
    try:
        resp = requests.post(f"{API_BASE}{path}", json=body, headers=headers, timeout=20)
        if resp.status_code == 429:
            print("⚠️ Creators API throttled (429). Backing off 2s and retrying once...")
            time.sleep(2)
            resp = requests.post(f"{API_BASE}{path}", json=body, headers=headers, timeout=20)
        data = resp.json()
        if resp.status_code >= 400:
            print(f"❌ Creators API {path} error {resp.status_code}: {data}")
            return None
        return data
    except Exception as e:
        print(f"❌ Creators API request failed ({path}): {e}")
        return None


def get_items(asins):
    """Fetch up to 10 products by ASIN. Returns a list of product dicts."""
    asins = [a for a in (asins or []) if a][:10]
    if not asins:
        return []
    print(f"🔍 Fetching {len(asins)} product(s) via Creators API...")
    body = {
        "itemIds": asins,
        "itemIdType": "ASIN",
        "resources": RESOURCES,
        "partnerTag": PARTNER_TAG,
        "partnerType": "Associates",
        "marketplace": MARKETPLACE,
    }
    data = _post("/catalog/v1/getItems", body)
    items = _dig(data, "itemResults", "items") or []
    if items:
        return [_map_item(i) for i in items]
    # Creators API returned nothing (e.g. account not eligible) -> fall back.
    if FALLBACK_ENABLED:
        return [d for d in (_rapidapi_get_item(a) for a in asins) if d]
    return []


def get_item(asin):
    """Fetch a single product by ASIN. Returns a product dict or None."""
    items = get_items([asin])
    return items[0] if items else None


def search_deals(keywords, search_index="All", min_saving_percent=None, item_count=10):
    """Search for deals by keyword. Returns a list of product dicts (may be empty)."""
    print(f"🔎 Searching Creators API: '{keywords}' (index={search_index})...")
    body = {
        "keywords": keywords,
        "searchIndex": search_index,
        "itemCount": min(item_count, 10),
        "resources": RESOURCES,
        "partnerTag": PARTNER_TAG,
        "partnerType": "Associates",
        "marketplace": MARKETPLACE,
    }
    if min_saving_percent:
        body["minSavingPercent"] = min_saving_percent
    data = _post("/catalog/v1/searchItems", body)
    # Response envelope not fully documented; try the likely candidates.
    items = (
        _dig(data, "searchResult", "items")
        or _dig(data, "itemResults", "items")
        or []
    )
    if items:
        return [_map_item(i) for i in items]
    # Creators API returned nothing (e.g. account not eligible) -> fall back.
    if FALLBACK_ENABLED:
        return _rapidapi_search(keywords, item_count=item_count)
    return []


# --- RapidAPI scraper fallback implementation --------------------------------

def _rapidapi_post(payload):
    if not RAPIDAPI_KEY:
        print("⚠️ RapidAPI fallback unavailable (RAPIDAPI_KEY not set).")
        return None
    url = f"https://{RAPIDAPI_HOST}/queries"
    headers = {
        "content-type": "application/json",
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }
    try:
        return requests.post(url, json=payload, headers=headers, timeout=20).json()
    except Exception as e:
        print(f"❌ RapidAPI fallback request failed: {e}")
        return None


def _tagged_url(base_url):
    if not base_url:
        return None
    sep = "&" if urllib.parse.urlparse(base_url).query else "?"
    return f"{base_url}{sep}tag={PARTNER_TAG}"


def _rapidapi_get_item(asin):
    print(f"⤵️ Falling back to RapidAPI scraper for ASIN {asin}...")
    res = _rapidapi_post({"source": "amazon_product", "query": asin, "geo_location": "90210", "parse": True})
    content = _dig(res, "results", 0, "content")
    if not content:
        return None
    pct = content.get("discount_percentage")
    images = content.get("images", []) or []
    return {
        "asin": asin,
        "title": content.get("title", "Amazing Amazon Find!"),
        "price": f"${content.get('price')}" if content.get("price") else "Check price",
        "old_price": None,
        "discount": f"{pct}%" if pct else None,
        "discount_text": f" ({pct}% OFF!)" if pct else "",
        "affiliate_url": _tagged_url(content.get("url", "")),
        "image_url": images[0] if images else None,
        "image_list": images[:5],
        "rating": content.get("rating"),
        "reviews_count": content.get("reviews_count"),
    }


def _rapidapi_search(keywords, item_count=10):
    print(f"⤵️ Falling back to RapidAPI scraper for search '{keywords}'...")
    res = _rapidapi_post({"source": "amazon_search", "query": keywords, "geo_location": "90210", "parse": True})
    content = _dig(res, "results", 0, "content") or {}
    organic = _dig(content, "results", "organic") or content.get("organic") or []
    deals = []
    for item in organic[:item_count]:
        asin = item.get("asin")
        if not asin:
            continue
        price = item.get("price", 0)
        old_price = item.get("price_strikethrough", 0)
        discount = None
        if old_price and price and old_price > price:
            discount = f"{round((old_price - price) / old_price * 100)}%"
        deals.append({
            "asin": asin,
            "title": item.get("title", "Amazing Amazon Find!"),
            "price": f"${price}" if price else "Check price",
            "old_price": f"${old_price}" if old_price else None,
            "discount": discount,
            "discount_text": f" ({discount} OFF!)" if discount else "",
            "affiliate_url": _tagged_url(f"https://www.amazon.com{item.get('url', '')}"),
            "image_url": item.get("url_image"),
            "image_list": [item.get("url_image")] if item.get("url_image") else [],
            "rating": item.get("rating"),
            "reviews_count": item.get("reviews_count"),
        })
    return deals
