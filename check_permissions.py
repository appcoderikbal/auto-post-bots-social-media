"""
Check what permissions are on your FB_PAGE_ACCESS_TOKEN.
Run via GitHub Actions — the token is never printed, only the scopes are shown.
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

token = os.getenv("FB_PAGE_ACCESS_TOKEN")
if not token:
    print("❌ FB_PAGE_ACCESS_TOKEN is not set in environment.")
    sys.exit(1)

print("🔍 Checking Facebook Page Access Token permissions...\n")

res = requests.get(
    "https://graph.facebook.com/debug_token",
    params={"input_token": token, "access_token": token},
    timeout=15
).json()

data = res.get("data", {})

if not data:
    print(f"❌ API Error: {res}")
    sys.exit(1)

# Print token info (no actual token value)
print(f"📋 Token Info:")
print(f"  Type       : {data.get('type', 'unknown')}")
print(f"  App ID     : {data.get('app_id', 'unknown')}")
print(f"  Valid      : {data.get('is_valid', False)}")
expires = data.get('expires_at', 0)
print(f"  Expires At : {'Never (long-lived)' if expires == 0 else expires}")
print()

# Print all scopes
scopes = data.get("scopes", [])
print(f"📋 Permissions on this token ({len(scopes)} total):")
for scope in sorted(scopes):
    print(f"  ✅ {scope}")

# Check for the specific permissions this project needs
print()
print("🎯 Required Permission Check:")
required = {
    "pages_manage_posts":         "Post to FB Page",
    "pages_manage_engagement":    "Pin comments on FB posts",
    "pages_read_engagement":      "Read FB comments for auto-reply",
    "instagram_content_publish":  "Post to Instagram",
    "instagram_manage_comments":  "Reply to IG comments",
    "instagram_basic":            "Read IG account info",
}

all_good = True
for perm, purpose in required.items():
    if perm in scopes:
        print(f"  ✅ {perm} ({purpose})")
    else:
        print(f"  ❌ MISSING: {perm} ({purpose})")
        all_good = False

print()
if all_good:
    print("✅ All required permissions are present!")
else:
    print("⚠️  Some permissions are missing.")
    print("   → Go to Meta Developer Console → Graph API Explorer")
    print("   → Select your Page → tick the missing permissions → Generate Token")
    print("   → Update FB_PAGE_ACCESS_TOKEN in GitHub Secrets")
