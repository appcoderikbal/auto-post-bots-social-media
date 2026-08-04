"""
Comment Auto-Reply Bot (Polling Mode)
======================================
Polls recent FB Page posts and IG media for comments asking for a link.
Replies automatically with a bio link message.

No server needed — runs via GitHub Actions triggered by cron-job.org.
Tracks replied comments in Supabase to avoid duplicate replies.

Supabase table required (create once):
  CREATE TABLE replied_comments (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    comment_id  TEXT UNIQUE NOT NULL,
    platform    TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
  );
"""

import os
import sys
import random
import requests
from dotenv import load_dotenv
from utils import supabase

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

# ── Config ──────────────────────────────────────────────────────────────────
FB_PAGE_ID      = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
IG_ACCOUNT_ID   = os.getenv("INSTAGRAM_ACCOUNT_ID")

# Number of recent posts/media to check each run
POSTS_TO_CHECK = 5

# Keywords that indicate someone is asking for the deal link
LINK_KEYWORDS = [
    "link", "url", "where", "how", "buy", "shop", "purchase",
    "send", "share", "get it", "get this", "order",
    "find", "source", "website", "site",
]

# Varied replies so it never looks like a spam bot
REPLIES = [
    "Hi! 😊 The link is in our bio — tap our profile to grab the deal! 👆",
    "Hey! 👋 Check our bio link for the full deal! 🔗",
    "The deal link is in our bio! Visit our profile and you'll find it right there ✨",
    "Hi there! 🛒 We've got the link in our bio — just tap our profile name! 💙",
    "The link is pinned in our bio 👆 Head to our profile to grab it! 🔥",
    "Hey! All our deals are linked in our bio — check it out! 😊",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _wants_link(text: str) -> bool:
    """Return True if the comment is asking for a link."""
    return any(kw in text.lower() for kw in LINK_KEYWORDS)


def _already_replied(comment_id: str) -> bool:
    """Check Supabase to see if we've already replied to this comment."""
    if not supabase:
        return False
    try:
        res = supabase.table("replied_comments") \
                      .select("id") \
                      .eq("comment_id", comment_id) \
                      .execute()
        return len(res.data) > 0
    except Exception as e:
        print(f"⚠️ Supabase check error: {e}")
        return False  # Reply anyway if check fails


def _mark_replied(comment_id: str, platform: str):
    """Save the comment ID to Supabase so we don't reply again."""
    if not supabase:
        return
    try:
        supabase.table("replied_comments").insert({
            "comment_id": comment_id,
            "platform":   platform
        }).execute()
    except Exception as e:
        print(f"⚠️ Could not save replied comment: {e}")


def _reply_fb(comment_id: str, message: str) -> bool:
    """Reply to a Facebook comment."""
    try:
        res = requests.post(
            f"https://graph.facebook.com/v19.0/{comment_id}/comments",
            data={"message": message, "access_token": FB_ACCESS_TOKEN},
            timeout=10
        ).json()
        if "id" in res:
            print(f"  ✅ FB reply sent → {comment_id}")
            return True
        print(f"  ⚠️ FB reply failed: {res}")
    except Exception as e:
        print(f"  ❌ FB reply error: {e}")
    return False


def _reply_ig(comment_id: str, message: str) -> bool:
    """Reply to an Instagram comment."""
    try:
        res = requests.post(
            f"https://graph.facebook.com/v19.0/{comment_id}/replies",
            data={"message": message, "access_token": FB_ACCESS_TOKEN},
            timeout=10
        ).json()
        if "id" in res:
            print(f"  ✅ IG reply sent → {comment_id}")
            return True
        print(f"  ⚠️ IG reply failed: {res}")
    except Exception as e:
        print(f"  ❌ IG reply error: {e}")
    return False


# ── Polling Functions ─────────────────────────────────────────────────────────

def poll_fb():
    """Check recent FB Page posts for comments asking for links."""
    print("\n📘 Polling Facebook comments...")
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        print("  ❌ FB credentials missing — skipping.")
        return

    try:
        res = requests.get(
            f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/posts",
            params={
                "fields": "id,comments{id,message,from,created_time}",
                "limit":  POSTS_TO_CHECK,
                "access_token": FB_ACCESS_TOKEN
            },
            timeout=15
        ).json()

        posts   = res.get("data", [])
        replied = 0

        for post in posts:
            comments = post.get("comments", {}).get("data", [])
            for c in comments:
                comment_id = c.get("id")
                text       = c.get("message", "")
                from_id    = c.get("from", {}).get("id", "")

                # Never reply to our own page comments
                if str(from_id) == str(FB_PAGE_ID):
                    continue

                if _wants_link(text) and not _already_replied(comment_id):
                    print(f"  🔗 Found link request: '{text[:60]}...' [{comment_id}]")
                    if _reply_fb(comment_id, random.choice(REPLIES)):
                        _mark_replied(comment_id, "fb")
                        replied += 1

        print(f"  📊 Done. Replied to {replied} new FB comment(s).")

    except Exception as e:
        print(f"  ❌ FB poll error: {e}")


def poll_ig():
    """Check recent IG media for comments asking for links."""
    print("\n📸 Polling Instagram comments...")
    if not IG_ACCOUNT_ID or not FB_ACCESS_TOKEN:
        print("  ❌ IG credentials missing — skipping.")
        return

    try:
        res = requests.get(
            f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media",
            params={
                "fields": "id,comments{id,text,username,timestamp}",
                "limit":  POSTS_TO_CHECK,
                "access_token": FB_ACCESS_TOKEN
            },
            timeout=15
        ).json()

        media_list = res.get("data", [])
        replied    = 0

        for media in media_list:
            comments = media.get("comments", {}).get("data", [])
            for c in comments:
                comment_id = c.get("id")
                text       = c.get("text", "")

                if _wants_link(text) and not _already_replied(comment_id):
                    print(f"  🔗 Found link request: '{text[:60]}' [{comment_id}]")
                    if _reply_ig(comment_id, random.choice(REPLIES)):
                        _mark_replied(comment_id, "ig")
                        replied += 1

        print(f"  📊 Done. Replied to {replied} new IG comment(s).")

    except Exception as e:
        print(f"  ❌ IG poll error: {e}")


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🤖 Comment Reply Bot starting...")
    poll_fb()
    poll_ig()
    print("\n✅ Comment polling complete.")
