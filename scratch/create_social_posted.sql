-- Run this in the Supabase SQL Editor.
-- Tracks what has already gone out to Facebook / Instagram so the
-- "best deal" picker never repeats a product (or a hook) too soon.

CREATE TABLE IF NOT EXISTS social_posted (
    id         UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    asin       TEXT        NOT NULL,
    platform   TEXT        NOT NULL,   -- 'fb' or 'ig'
    post_id    TEXT,                   -- FB post id / IG media id
    hook       TEXT,                   -- which opening line was used
    title      TEXT,
    score      NUMERIC,                -- why this deal won
    posted_at  TIMESTAMPTZ DEFAULT now()
);

-- One record per ASIN per platform — upsert refreshes it on a repost
CREATE UNIQUE INDEX IF NOT EXISTS social_posted_asin_platform
    ON social_posted (asin, platform);

-- Fast "have we posted this / what did we post lately" lookups
CREATE INDEX IF NOT EXISTS social_posted_platform_time
    ON social_posted (platform, posted_at DESC);


-- ── Row Level Security ──────────────────────────────────────────────────────
-- Supabase turns RLS on for new tables, which blocks every write from the
-- `anon` key:
--     new row violates row-level security policy for table "social_posted"
--
-- The bot must therefore authenticate with the **service_role** key, which
-- bypasses RLS. That is what the SUPABASE_KEY GitHub secret needs to be.
-- Settings -> API -> Project API keys -> service_role (keep it secret; it is
-- not the `anon` key the website uses).
--
-- RLS stays enabled so the public anon key cannot touch this table. It holds
-- no user data and nothing client-side needs to read it.
ALTER TABLE social_posted ENABLE ROW LEVEL SECURITY;

-- Only if you must keep writing with the anon key (NOT recommended -- that
-- key is public, so anyone could write junk into your post history):
--
-- CREATE POLICY "anon full access" ON social_posted
--     FOR ALL TO anon USING (true) WITH CHECK (true);


-- ── Heads up: the same applies to the existing tables ───────────────────────
-- telegram_queue and product_links reject anon writes with the identical
-- error, and both are currently empty. Whatever key fixes this table fixes
-- those two as well.
