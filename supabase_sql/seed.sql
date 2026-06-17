-- Supabase Schema for CustoDoce
-- Execute this in Supabase SQL Editor

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- PRICES TABLE (main data)
-- ============================================================================
CREATE TABLE IF NOT EXISTS prices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ingredient_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'automated',
    store_name TEXT NOT NULL DEFAULT '',
    raw_product TEXT NOT NULL,
    raw_price DECIMAL(10,2) NOT NULL,
    raw_unit TEXT NOT NULL DEFAULT '',
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_from DATE DEFAULT CURRENT_DATE,
    valid_until DATE DEFAULT (CURRENT_DATE + INTERVAL '7 days'),
    validity_raw TEXT DEFAULT '',
    collected_weekday TEXT DEFAULT '',
    is_promotion BOOLEAN DEFAULT FALSE,
    tier INTEGER DEFAULT 3,
    confidence DECIMAL(4,3) DEFAULT 1.0,
    normalized JSONB DEFAULT NULL,
    city TEXT DEFAULT '',
    logistics TEXT DEFAULT 'pickup_local',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (ingredient_id, store_id, collected_at)
);

-- Indexes for fast search
CREATE INDEX IF NOT EXISTS idx_prices_ingredient ON prices(ingredient_id);
CREATE INDEX IF NOT EXISTS idx_prices_store ON prices(store_id);
CREATE INDEX IF NOT EXISTS idx_prices_collected ON prices(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_prices_valid_from ON prices(valid_from);
CREATE INDEX IF NOT EXISTS idx_prices_valid_until ON prices(valid_until);
CREATE INDEX IF NOT EXISTS idx_prices_promotion ON prices(is_promotion) WHERE is_promotion = TRUE;
CREATE INDEX IF NOT EXISTS idx_prices_weekday ON prices(collected_weekday);
CREATE INDEX IF NOT EXISTS idx_prices_tier ON prices(tier);
CREATE INDEX IF NOT EXISTS idx_prices_confidence ON prices(confidence);
CREATE INDEX IF NOT EXISTS idx_prices_price_kg ON prices(((normalized->>'price_per_kg')::numeric));
CREATE INDEX IF NOT EXISTS idx_prices_logistics ON prices(logistics);
CREATE INDEX IF NOT EXISTS idx_prices_city ON prices(city);

-- ============================================================================
-- PRICE HISTORY TABLE (for trends)
-- ============================================================================
CREATE TABLE IF NOT EXISTS price_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    price_id UUID REFERENCES prices(id) ON DELETE SET NULL,
    ingredient_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    store_name TEXT NOT NULL DEFAULT '',
    raw_product TEXT NOT NULL,
    raw_price DECIMAL(10,2) NOT NULL,
    raw_unit TEXT NOT NULL DEFAULT '',
    normalized JSONB DEFAULT NULL,
    valid_from DATE DEFAULT CURRENT_DATE,
    valid_until DATE DEFAULT (CURRENT_DATE + INTERVAL '7 days'),
    validity_raw TEXT DEFAULT '',
    collected_weekday TEXT DEFAULT '',
    is_promotion BOOLEAN DEFAULT FALSE,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (ingredient_id, store_id, collected_at)
);

CREATE INDEX IF NOT EXISTS idx_history_ingredient ON price_history(ingredient_id);
CREATE INDEX IF NOT EXISTS idx_history_collected ON price_history(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_store ON price_history(store_id);
CREATE INDEX IF NOT EXISTS idx_history_valid_until ON price_history(valid_until);
CREATE INDEX IF NOT EXISTS idx_history_promotion ON price_history(is_promotion) WHERE is_promotion = TRUE;

-- ============================================================================
-- REVIEW QUEUE (confidence < 80%)
-- ============================================================================
CREATE TABLE IF NOT EXISTS review_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_product TEXT NOT NULL,
    raw_price DECIMAL(10,2),
    raw_unit TEXT,
    store_name TEXT,
    source TEXT DEFAULT 'automated',
    confidence DECIMAL(4,3),
    suggestions JSONB DEFAULT '[]',
    validity_raw TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    resolved_ingredient TEXT,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_review_status ON review_queue(status);

-- ============================================================================
-- SCRAPING LOG TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS scraping_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    store_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'started',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    items_found INTEGER DEFAULT 0,
    items_matched INTEGER DEFAULT 0,
    errors JSONB DEFAULT '[]',
    duration_seconds INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_scraping_logs_store ON scraping_logs(store_name);
CREATE INDEX IF NOT EXISTS idx_scraping_logs_status ON scraping_logs(status);
CREATE INDEX IF NOT EXISTS idx_scraping_logs_started ON scraping_logs(started_at DESC);

-- ============================================================================
-- STORES METADATA (mirror of stores.yaml for reference in DB)
-- ============================================================================
CREATE TABLE IF NOT EXISTS stores (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    tier INTEGER NOT NULL DEFAULT 3,
    type TEXT NOT NULL DEFAULT 'manual',
    logistics TEXT DEFAULT 'pickup_local',
    city TEXT DEFAULT '',
    zone TEXT DEFAULT '',
    coverage TEXT DEFAULT '',
    collection_method TEXT DEFAULT 'manual',
    is_active BOOLEAN DEFAULT TRUE,
    config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stores_tier ON stores(tier);
CREATE INDEX IF NOT EXISTS idx_stores_active ON stores(is_active);

-- ============================================================================
-- FLYERS TABLE (aggregator metadata + OCR pipeline)
-- ============================================================================
CREATE TABLE IF NOT EXISTS flyers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    store_name TEXT NOT NULL,
    region TEXT NOT NULL,
    city TEXT NOT NULL DEFAULT '',
    flyer_title TEXT DEFAULT '',
    flyer_date_start DATE,
    flyer_date_end DATE,
    image_url TEXT NOT NULL,
    image_hash TEXT DEFAULT '',
    image_type TEXT DEFAULT 'webp',
    image_width INT DEFAULT 0,
    image_height INT DEFAULT 0,
    ocr_status TEXT NOT NULL DEFAULT 'pending',
    ocr_text TEXT DEFAULT '',
    ocr_confidence DECIMAL(4,3) DEFAULT 0.0,
    products_extracted INT DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'tiendeo',
    valid_from DATE,
    valid_until DATE,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,

    UNIQUE (store_name, region, image_hash)
);

CREATE INDEX IF NOT EXISTS idx_flyers_ocr_status ON flyers(ocr_status);
CREATE INDEX IF NOT EXISTS idx_flyers_region ON flyers(region);
CREATE INDEX IF NOT EXISTS idx_flyers_collected ON flyers(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_flyers_source ON flyers(source);

-- ============================================================================
-- ROW LEVEL SECURITY (for future multi-tenant)
-- ============================================================================
ALTER TABLE prices ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraping_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE stores ENABLE ROW LEVEL SECURITY;
ALTER TABLE flyers ENABLE ROW LEVEL SECURITY;

-- Policies: allow all authenticated users (for now, single user mode)
CREATE POLICY "Enable read for all users" ON prices FOR SELECT USING (true);
CREATE POLICY "Enable write for service role" ON prices FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable update for service role" ON prices FOR UPDATE USING (true);

CREATE POLICY "Enable read for all users" ON price_history FOR SELECT USING (true);
CREATE POLICY "Enable write for service role" ON price_history FOR INSERT WITH CHECK (true);

CREATE POLICY "Enable read for all users" ON review_queue FOR SELECT USING (true);
CREATE POLICY "Enable write for service role" ON review_queue FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable update for service role" ON review_queue FOR UPDATE USING (true);

CREATE POLICY "Enable read for all users" ON scraping_logs FOR SELECT USING (true);
CREATE POLICY "Enable write for service role" ON scraping_logs FOR INSERT WITH CHECK (true);

CREATE POLICY "Enable read for all users" ON stores FOR SELECT USING (true);
CREATE POLICY "Enable write for service role" ON stores FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable update for service role" ON stores FOR UPDATE USING (true);

CREATE POLICY "Enable read for all users" ON flyers FOR SELECT USING (true);
CREATE POLICY "Enable write for service role" ON flyers FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable update for service role" ON flyers FOR UPDATE USING (true);

-- ============================================================================
-- FUNCTIONS
-- ============================================================================
CREATE OR REPLACE FUNCTION update_history_from_prices()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO price_history (
        price_id, ingredient_id, store_id, store_name,
        raw_product, raw_price, raw_unit, normalized,
        valid_from, valid_until, validity_raw, collected_weekday, is_promotion,
        collected_at
    ) VALUES (
        NEW.id, NEW.ingredient_id, NEW.store_id, NEW.store_name,
        NEW.raw_product, NEW.raw_price, NEW.raw_unit, NEW.normalized,
        NEW.valid_from, NEW.valid_until, NEW.validity_raw, NEW.collected_weekday, NEW.is_promotion,
        NEW.collected_at
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger: copy price to history on upsert
DROP TRIGGER IF EXISTS trg_price_history ON prices;
CREATE TRIGGER trg_price_history
    AFTER INSERT OR UPDATE ON prices
    FOR EACH ROW
    EXECUTE FUNCTION update_history_from_prices();
