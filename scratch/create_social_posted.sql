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
