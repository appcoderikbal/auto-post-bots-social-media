-- Run this in the Supabase SQL Editor.
--
-- WHY: snagpop.com/l/<asin> looks the ASIN up in product_links using the
-- PUBLIC anon key. Row Level Security denies that read, and an RLS denial on
-- SELECT returns zero rows *silently* rather than erroring -- so the page sits
-- on "Verifying direct offer details..." forever instead of redirecting.
--
-- The bot writes with a privileged key and is unaffected, which is why posting
-- looks healthy while every published link hangs.
--
-- FIX: let anon READ product_links. Writes stay restricted.
-- These rows are public affiliate links that already appear in public posts,
-- so there is nothing secret to protect here.

ALTER TABLE product_links ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read product_links" ON product_links;
CREATE POLICY "public read product_links"
    ON product_links
    FOR SELECT
    TO anon, authenticated
    USING (true);

-- Deliberately NO insert/update/delete policy for anon: only the service_role
-- key (which bypasses RLS) may write. The anon key is embedded in the website
-- and is effectively public.


-- ── Verify ──────────────────────────────────────────────────────────────────
-- The SQL Editor runs as a privileged role and bypasses RLS, so this shows
-- the true contents regardless of policy:
--
--     SELECT count(*) FROM product_links;
--     SELECT count(*) FROM social_posted;
--     SELECT asin, platform, posted_at FROM social_posted
--       ORDER BY posted_at DESC LIMIT 10;
--
-- If social_posted has rows, the bot's key is writing correctly and only the
-- website's read path needed fixing.

-- social_posted stays locked down -- nothing client-side reads it.
