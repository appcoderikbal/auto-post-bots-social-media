"""
Meta Webhook Server — Auto-reply to comments on FB & IG posts/reels.

When someone comments anything asking for a link (e.g. "link", "where",
"how to buy", "send me"), the bot replies:
  "Hi! We've added the link in our bio — check it out! 👆"

This works for both Facebook posts/reels AND Instagram posts/reels.

────────────────────────────────────────────────────────────
SETUP (one-time):
────────────────────────────────────────────────────────────
1. pip install flask
2. Add to .env:
     WEBHOOK_VERIFY_TOKEN=snagpop_secret   ← pick any secret string
     META_APP_SECRET=<from Meta App Dashboard → Settings → Basic>
     FB_PAGE_ACCESS_TOKEN=<your token>
     FB_PAGE_ID=<your FB page numeric ID>
     INSTAGRAM_ACCOUNT_ID=<your IG account ID>

3. Run locally + expose via ngrok:
     python webhook_server.py
     ngrok http 5000

   OR deploy to Railway/Render (free tier) for 24/7 uptime.

4. Register webhook in Meta Developer Console:
     App Dashboard → Webhooks → Add New Subscription
     Callback URL : https://YOUR_DOMAIN/webhook
     Verify Token : snagpop_secret   ← same as WEBHOOK_VERIFY_TOKEN

   Subscribe to:
     • Facebook Page  → field: "feed"        (catches FB comments/reels)
     • Instagram      → field: "comments"    (catches IG comments/reels)

5. Make sure your Meta App has these permissions approved:
     pages_manage_engagement   (to reply to FB comments)
     instagram_manage_comments (to reply to IG comments)
────────────────────────────────────────────────────────────
"""

import os
import random
import hashlib
import hmac
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ── Config ─────────────────────────────────────────────────────────────────
VERIFY_TOKEN       = os.getenv("WEBHOOK_VERIFY_TOKEN", "snagpop_secret")
FB_ACCESS_TOKEN    = os.getenv("FB_PAGE_ACCESS_TOKEN")
APP_SECRET         = os.getenv("META_APP_SECRET")       # For payload verification
OWN_PAGE_ID        = os.getenv("FB_PAGE_ID")            # Skip replying to own FB comments
OWN_IG_ID          = os.getenv("INSTAGRAM_ACCOUNT_ID")  # Skip replying to own IG comments

# ── Keywords that suggest someone is asking for the deal link ───────────────
LINK_KEYWORDS = [
    "link", "url", "where", "how", "buy", "shop", "purchase",
    "send", "dm", "share", "get it", "get this", "order",
    "price", "cost", "available", "find", "source", "site",
]

# ── Varied replies so the bot doesn't look spammy ──────────────────────────
BIO_REPLIES = [
    "Hi! 😊 We've added the link in our bio — head to our profile and check it out! 👆",
    "Hey! 👋 The deal link is in our bio right now. Just tap our profile name to find it! 🔗",
    "The link is in the bio! 🔗 Visit our profile page and grab the deal — don't miss it! ✨",
    "😊 Great timing! The deal link is in our bio — go check it out! 👆",
    "Hi there! 🛒 The link is in our bio. Tap our profile name and you'll see it right away! 💙",
    "Hey! We've got the link pinned in our bio 👆 Tap our profile to grab the deal! 🔥",
    "The deal is live! 🛒 Check our bio link for the full details and grab it while it lasts! ✨",
]


# ── Helpers ─────────────────────────────────────────────────────────────────

def _wants_link(text: str) -> bool:
    """Return True if the comment is asking for a link/deal."""
    lowered = text.lower()
    return any(kw in lowered for kw in LINK_KEYWORDS)


def _verify_signature(payload: bytes, sig_header: str) -> bool:
    """
    Validate Meta's X-Hub-Signature-256 header so we only process
    genuine events from Meta — not spoofed requests.
    """
    if not APP_SECRET:
        # Dev mode: skip verification if secret is not configured yet
        return True
    if not sig_header or not sig_header.startswith("sha256="):
        return False
    try:
        expected = "sha256=" + hmac.new(
            APP_SECRET.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, sig_header)
    except Exception:
        return False


def _reply_ig(comment_id: str, message: str):
    """Reply to an Instagram comment."""
    try:
        res = requests.post(
            f"https://graph.facebook.com/v19.0/{comment_id}/replies",
            data={"message": message, "access_token": FB_ACCESS_TOKEN},
            timeout=10,
        ).json()
        if "id" in res:
            print(f"✅ IG reply sent → comment {comment_id}")
        else:
            print(f"⚠️  IG reply failed: {res}")
    except Exception as e:
        print(f"❌ IG reply error: {e}")


def _reply_fb(comment_id: str, message: str):
    """Reply to a Facebook comment (on post or reel)."""
    try:
        res = requests.post(
            f"https://graph.facebook.com/v19.0/{comment_id}/comments",
            data={"message": message, "access_token": FB_ACCESS_TOKEN},
            timeout=10,
        ).json()
        if "id" in res:
            print(f"✅ FB reply sent → comment {comment_id}")
        else:
            print(f"⚠️  FB reply failed: {res}")
    except Exception as e:
        print(f"❌ FB reply error: {e}")


# ── Webhook Routes ───────────────────────────────────────────────────────────

@app.route("/webhook", methods=["GET"])
def verify():
    """
    Meta verification handshake.
    Meta sends a GET request when you first register the webhook URL.
    We echo back hub.challenge to confirm we own this endpoint.
    """
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verified by Meta!")
        return challenge, 200
    print("❌ Webhook verification failed — wrong token?")
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def handle_event():
    """
    Receive and process webhook events.
    Handles:
      - Instagram comment events  (object = "instagram", field = "comments")
      - Facebook comment events   (object = "page",      field = "feed", item = "comment")
    """
    # Verify the request is genuinely from Meta
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_signature(request.data, sig):
        print("❌ Invalid webhook signature — request ignored.")
        return "Unauthorized", 401

    data = request.get_json(silent=True) or {}
    obj  = data.get("object")

    # ── Instagram Comments ───────────────────────────────────────────────────
    if obj == "instagram":
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") != "comments":
                    continue

                val        = change.get("value", {})
                comment_id = val.get("id")
                text       = val.get("text", "")
                from_id    = val.get("from", {}).get("id", "")

                # Never reply to our own comments (would cause an infinite loop)
                if str(from_id) == str(OWN_IG_ID):
                    continue

                print(f"📩 IG comment [{comment_id}] from {from_id}: '{text}'")

                if comment_id and _wants_link(text):
                    print(f"🔗 Triggering bio reply for IG comment {comment_id}...")
                    _reply_ig(comment_id, random.choice(BIO_REPLIES))

    # ── Facebook Page Comments / Reels ───────────────────────────────────────
    elif obj == "page":
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") != "feed":
                    continue

                val        = change.get("value", {})
                # Only process comment events (not likes, shares, etc.)
                if val.get("item") != "comment":
                    continue

                comment_id = val.get("comment_id")
                text       = val.get("message", "")
                from_id    = val.get("from", {}).get("id", "")

                # Never reply to our own comments
                if str(from_id) == str(OWN_PAGE_ID):
                    continue

                print(f"📩 FB comment [{comment_id}] from {from_id}: '{text}'")

                if comment_id and _wants_link(text):
                    print(f"🔗 Triggering bio reply for FB comment {comment_id}...")
                    _reply_fb(comment_id, random.choice(BIO_REPLIES))

    # Meta expects a 200 back quickly, even if processing takes time
    return jsonify({"status": "ok"}), 200


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Webhook server starting on port {port}...")
    print(f"📡 Listening at: http://0.0.0.0:{port}/webhook")
    app.run(host="0.0.0.0", port=port, debug=False)
