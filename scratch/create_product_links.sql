-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS product_links (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    asin         TEXT        NOT NULL,
    region       TEXT        NOT NULL,   -- 'us' or 'in'
    affiliate_url TEXT,
    title        TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- One record per ASIN per region, upsert updates it on refresh
CREATE UNIQUE INDEX IF NOT EXISTS product_links_asin_region
    ON product_links (asin, region);

-- Fast lookup by ASIN (used by snagpop.com website)
CREATE INDEX IF NOT EXISTS product_links_asin
    ON product_links (asin);
