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
import re
import time
import urllib.parse
import requests
from dotenv import load_dotenv

load_dotenv()

# --- Config generator per region ----------
def get_config(region="us"):
    if region == "in":
        return {
            "client_id": os.getenv("AMAZON_CREATORS_CLIENT_ID_IN"),
            "client_secret": os.getenv("AMAZON_CREATORS_CLIENT_SECRET_IN"),
            "partner_tag": os.getenv("AMAZON_CREATORS_PARTNER_TAG_IN", "your-in-tag"),
            "marketplace": os.getenv("AMAZON_MARKETPLACE_IN", "www.amazon.in"),
            "country": "IN",
        }
    else:
        return {
            "client_id": os.getenv("AMAZON_CREATORS_CLIENT_ID_US") or os.getenv("AMAZON_CREATORS_CLIENT_ID"),
            "client_secret": os.getenv("AMAZON_CREATORS_CLIENT_SECRET_US") or os.getenv("AMAZON_CREATORS_CLIENT_SECRET"),
            "partner_tag": os.getenv("AMAZON_CREATORS_PARTNER_TAG_US") or os.getenv("AMAZON_CREATORS_PARTNER_TAG") or os.getenv("AMAZON_ASSOCIATE_TAG", "dealducker09-20"),
            "marketplace": os.getenv("AMAZON_MARKETPLACE_US") or os.getenv("AMAZON_MARKETPLACE", "www.amazon.com"),
            "country": "US",
        }

# Overridable in case Amazon changes hosts/scopes.
TOKEN_URL = os.getenv("AMAZON_TOKEN_URL", "https://api.amazon.com/auth/o2/token")
API_BASE = os.getenv("AMAZON_CREATORS_API_BASE", "https://creatorsapi.amazon")
SCOPE = os.getenv("AMAZON_CREATORS_SCOPE", "creatorsapi::default")

# --- Fallback: Real-Time Amazon Data (RapidAPI) ------------------------------
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
REALTIME_AMAZON_HOST = os.getenv("REALTIME_AMAZON_HOST", "real-time-amazon-data.p.rapidapi.com")
FALLBACK_ENABLED = os.getenv("AMAZON_FALLBACK_ENABLED", "true").lower() == "true"

RESOURCES = [
    "itemInfo.title",
    "images.primary.large",
    "images.variants.large",
    "offersV2.listings.price",
    "customerReviews.starRating",
    "customerReviews.count",
]

_tokens = {"us": {"value": None, "expires_at": 0.0}, "in": {"value": None, "expires_at": 0.0}}

def _get_token(region="us"):
    """Return a cached bearer token, refreshing via OAuth2 when expired."""
    now = time.time()
    token_cache = _tokens.setdefault(region, {"value": None, "expires_at": 0.0})
    if token_cache["value"] and now < token_cache["expires_at"] - 60:
        return token_cache["value"]
        
    cfg = get_config(region)
    if not (cfg["client_id"] and cfg["client_secret"]):
        print(f"⚠️ Amazon Creators API credentials missing for region '{region}'.")
        return None
    try:
        res = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "scope": SCOPE,
            },
            timeout=15,
        ).json()
        token = res.get("access_token")
        if token:
            token_cache["value"] = token
            token_cache["expires_at"] = now + int(res.get("expires_in", 3600))
            return token
        print(f"❌ Token error for {region}: {res}")
    except Exception as e:
        print(f"❌ Token request failed for {region}: {e}")
    return None

def _headers(region="us"):
    token = _get_token(region)
    if not token:
        return None
    cfg = get_config(region)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "x-marketplace": cfg["marketplace"],
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


def _map_item(item, region="us"):
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


def _post(path, body, region="us"):
    """POST a JSON body to a Creators API endpoint; return parsed JSON or None."""
    headers = _headers(region)
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


def get_items(asins, region="us"):
    """Fetch up to 10 products by ASIN. Returns a list of product dicts."""
    asins = [a for a in (asins or []) if a][:10]
    if not asins:
        return []
    print(f"🔍 Fetching {len(asins)} product(s) via Creators API...")
    body = {
        "itemIds": asins,
        "itemIdType": "ASIN",
        "resources": RESOURCES,
        "partnerTag": get_config(region)["partner_tag"],
        "partnerType": "Associates",
        "marketplace": get_config(region)["marketplace"],
    }
    data = _post("/catalog/v1/getItems", body, region=region)
    items = _dig(data, "itemResults", "items") or []
    if items:
        return [_map_item(i, region) for i in items]
    # Creators API returned nothing (e.g. account not eligible) -> fall back.
    if FALLBACK_ENABLED:
        return [d for d in (_rapidapi_get_item(a, region) for a in asins) if d]
    return []


def get_item(asin, region="us"):
    """Fetch a single product by ASIN. Returns a product dict or None."""
    items = get_items([asin], region)
    return items[0] if items else None


def search_deals(keywords, search_index="All", min_saving_percent=None, item_count=10, region="us"):
    """Search for deals by keyword. Returns a list of product dicts (may be empty)."""
    print(f"🔎 Searching Creators API: '{keywords}' (index={search_index})...")
    body = {
        "keywords": keywords,
        "searchIndex": search_index,
        "itemCount": min(item_count, 10),
        "resources": RESOURCES,
        "partnerTag": get_config(region)["partner_tag"],
        "partnerType": "Associates",
        "marketplace": get_config(region)["marketplace"],
    }
    if min_saving_percent:
        body["minSavingPercent"] = min_saving_percent
    data = _post("/catalog/v1/searchItems", body, region=region)
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
        return _rapidapi_search(keywords, item_count=item_count, region=region)
    return []


# --- Real-Time Amazon Data (RapidAPI) fallback implementation ----------------

def _rtad_get(path, params):
    """GET a Real-Time Amazon Data endpoint; return parsed JSON or None."""
    if not RAPIDAPI_KEY:
        print("⚠️ Fallback unavailable (RAPIDAPI_KEY not set).")
        return None
    url = f"https://{REALTIME_AMAZON_HOST}{path}"
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": REALTIME_AMAZON_HOST}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        if resp.status_code != 200:
            print(f"❌ Real-Time Amazon Data HTTP {resp.status_code}: {resp.text[:300]}")
            return None
        return resp.json()
    except Exception as e:
        print(f"❌ Real-Time Amazon Data request failed: {e}")
        return None


def _parse_price(value):
    """Parse a price string like '$1,299.99' into a float, or None."""
    if value in (None, ""):
        return None
    try:
        return float(re.sub(r"[^0-9.]", "", str(value)))
    except ValueError:
        return None


def _tagged_url(base_url, region="us"):
    if not base_url:
        return None
    sep = "&" if urllib.parse.urlparse(base_url).query else "?"
    return f"{base_url}{sep}tag={get_config(region)['partner_tag']}"


def _map_rtad(p, region="us"):
    """Map a Real-Time Amazon Data product dict to the project's standard dict."""
    price_disp = p.get("product_price")
    old_disp = p.get("product_original_price")
    cur, old = _parse_price(price_disp), _parse_price(old_disp)
    pct = round((old - cur) / old * 100) if (old and cur and old > cur) else None
    photos = p.get("product_photos") or ([p.get("product_photo")] if p.get("product_photo") else [])
    return {
        "asin": p.get("asin"),
        "title": p.get("product_title", "Amazing Amazon Find!"),
        "price": price_disp or "Check price",
        "old_price": old_disp,
        "discount": f"{pct}%" if pct else None,
        "discount_text": f" ({pct}% OFF!)" if pct else "",
        "affiliate_url": _tagged_url(p.get("product_url"), region),
        "image_url": photos[0] if photos else None,
        "image_list": [ph for ph in photos if ph][:5],
        "rating": p.get("product_star_rating"),
        "reviews_count": p.get("product_num_ratings"),
    }


def _rapidapi_get_item(asin, region="us"):
    print(f"⤵️ Fetching ASIN {asin} via Real-Time Amazon Data...")
    data = _rtad_get("/product-details", {"asin": asin, "country": get_config(region)["country"]})
    product = _dig(data, "data")
    if not product:
        if data is not None:
            print(f"⚠️ No product data for {asin}. Keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
        return None
    return _map_rtad(product, region)


def _rapidapi_search(keywords, item_count=10, region="us"):
    print(f"⤵️ Searching '{keywords}' via Real-Time Amazon Data...")
    data = _rtad_get("/search", {"query": keywords, "country": get_config(region)["country"], "page": "1"})
    products = _dig(data, "data", "products") or []
    if not products and data is not None:
        print(f"⚠️ Real-Time Amazon Data returned no products. "
              f"Keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
    return [_map_rtad(p, region) for p in products[:item_count] if p.get("asin")]
