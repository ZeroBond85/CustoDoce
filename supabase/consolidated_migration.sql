-- ============================================================
-- PHASE 1: Core tables (seed.sql)
-- ============================================================
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
-- SCRAPER HEALTH LOG (failure/success events for self-healing)
-- ============================================================================
CREATE TABLE IF NOT EXISTS scraper_health_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scraper_name TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('failure', 'success', 'auto_disabled', 'auto_reactivated')),
    error_class TEXT,
    reason TEXT,
    failures_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    attempted_by TEXT DEFAULT 'auto',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scraper_health_log_name ON scraper_health_log(scraper_name);
CREATE INDEX IF NOT EXISTS idx_scraper_health_log_type ON scraper_health_log(event_type);
CREATE INDEX IF NOT EXISTS idx_scraper_health_log_created ON scraper_health_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scraper_health_log_name_type ON scraper_health_log(scraper_name, event_type);

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
    priority INTEGER DEFAULT 99,
    config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stores_tier ON stores(tier);
CREATE INDEX IF NOT EXISTS idx_stores_active ON stores(is_active);
CREATE INDEX IF NOT EXISTS idx_stores_priority ON stores(priority);

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
        collected_at, brand
    ) VALUES (
        NEW.id, NEW.ingredient_id, NEW.store_id, NEW.store_name,
        NEW.raw_product, NEW.raw_price, NEW.raw_unit, NEW.normalized,
        NEW.valid_from, NEW.valid_until, NEW.validity_raw, NEW.collected_weekday, NEW.is_promotion,
        NEW.collected_at, NEW.brand
    )
    ON CONFLICT (ingredient_id, store_id, collected_at)
    DO UPDATE SET
        price_id = EXCLUDED.price_id,
        raw_price = EXCLUDED.raw_price,
        raw_product = EXCLUDED.raw_product,
        raw_unit = EXCLUDED.raw_unit,
        valid_from = EXCLUDED.valid_from,
        valid_until = EXCLUDED.valid_until,
        validity_raw = EXCLUDED.validity_raw,
        is_promotion = EXCLUDED.is_promotion,
        collected_weekday = EXCLUDED.collected_weekday,
        brand = EXCLUDED.brand;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger: copy price to history on upsert
DROP TRIGGER IF EXISTS trg_price_history ON prices;
CREATE TRIGGER trg_price_history
    AFTER INSERT OR UPDATE ON prices
    FOR EACH ROW
    EXECUTE FUNCTION update_history_from_prices();


-- ============================================================
-- PHASE 2: Validity/promotion columns (migration_vigencia.sql)
-- ============================================================
-- CustoDoce — Migration: Vigência, Promoção e Weekday
-- Executar no Supabase SQL Editor após seed.sql

-- ============================================================================
-- PRICES: add new columns (safe: IF NOT EXISTS)
-- ============================================================================
ALTER TABLE prices ADD COLUMN IF NOT EXISTS valid_from DATE DEFAULT CURRENT_DATE;
ALTER TABLE prices ADD COLUMN IF NOT EXISTS validity_raw TEXT DEFAULT '';
ALTER TABLE prices ADD COLUMN IF NOT EXISTS collected_weekday TEXT DEFAULT '';
ALTER TABLE prices ADD COLUMN IF NOT EXISTS is_promotion BOOLEAN DEFAULT FALSE;

-- Update existing rows: valid_until default +7 dias if NULL
UPDATE prices SET valid_until = collected_at::DATE + INTERVAL '7 days' WHERE valid_until IS NULL;
ALTER TABLE prices ALTER COLUMN valid_until SET DEFAULT (CURRENT_DATE + INTERVAL '7 days');

-- ============================================================================
-- PRICE HISTORY: add new columns
-- ============================================================================
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS valid_from DATE DEFAULT CURRENT_DATE;
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS valid_until DATE DEFAULT (CURRENT_DATE + INTERVAL '7 days');
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS validity_raw TEXT DEFAULT '';
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS collected_weekday TEXT DEFAULT '';
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS is_promotion BOOLEAN DEFAULT FALSE;

-- ============================================================================
-- REVIEW QUEUE: add validity_raw
-- ============================================================================
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS validity_raw TEXT DEFAULT '';

-- ============================================================================
-- FLYERS: add valid_from, valid_until
-- ============================================================================
ALTER TABLE flyers ADD COLUMN IF NOT EXISTS valid_from DATE;
ALTER TABLE flyers ADD COLUMN IF NOT EXISTS valid_until DATE;

-- ============================================================================
-- INDEXES for new columns
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_prices_valid_from ON prices(valid_from);
CREATE INDEX IF NOT EXISTS idx_prices_valid_until ON prices(valid_until);
CREATE INDEX IF NOT EXISTS idx_prices_promotion ON prices(is_promotion) WHERE is_promotion = TRUE;
CREATE INDEX IF NOT EXISTS idx_prices_weekday ON prices(collected_weekday);
CREATE INDEX IF NOT EXISTS idx_history_valid_until ON price_history(valid_until);
CREATE INDEX IF NOT EXISTS idx_history_promotion ON price_history(is_promotion) WHERE is_promotion = TRUE;

-- ============================================================================
-- UPDATE trigger to include new columns
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

-- ============================================================================
-- Update UNIQUE constraint to include collected_at
-- ============================================================================
-- Drop old unique and recreate with collected_at
ALTER TABLE prices DROP CONSTRAINT IF EXISTS prices_ingredient_id_store_id_key;
ALTER TABLE prices ADD CONSTRAINT prices_ingredient_id_store_id_collected_at_key UNIQUE (ingredient_id, store_id, collected_at);


-- ============================================================
-- PHASE 3: Config tables (001_config_tables.sql, adapted)
-- ============================================================
-- Migration 001: Config tables for CustoDoce
-- Run this in Supabase SQL Editor

-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- ============================================================
-- INGREDIENTS (replace config/ingredients.yaml)
-- ============================================================
create table if not exists ingredients (
    id uuid primary key default gen_random_uuid(),
    canonical_name text unique not null,
    category text,
    aliases text[] default '{}',
    unit_target text default 'kg',
    active boolean default true,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_ingredients_active on ingredients(active);
create index if not exists idx_ingredients_category on ingredients(category);

-- Trigger for updated_at
create or replace function update_updated_at_column()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end; $$;

drop trigger if exists trg_ingredients_updated_at on ingredients;
create trigger trg_ingredients_updated_at
    before update on ingredients
    for each row execute function update_updated_at_column();

-- ============================================================
-- STORES (replace config/stores.yaml)
-- ============================================================
-- SKIPPED: stores table already exists from seed.sql
create index if not exists idx_stores_active on stores(active);
create index if not exists idx_stores_tier on stores(tier);
create index if not exists idx_stores_type on stores(type);
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='stores' AND column_name='scraper') THEN
        CREATE INDEX IF NOT EXISTS idx_stores_scraper ON stores(scraper);
    END IF;
END $$;

drop trigger if exists trg_stores_updated_at on stores;
create trigger trg_stores_updated_at
    before update on stores
    for each row execute function update_updated_at_column();

-- ============================================================
-- SCHEDULES (replace GitHub Actions cron)
-- ============================================================
create table if not exists schedules (
    id uuid primary key default gen_random_uuid(),
    name text unique not null,
    cron_expression text not null,
    timezone text default 'America/Sao_Paulo',
    payload jsonb default '{}',
    enabled boolean default true,
    last_run timestamptz,
    next_run timestamptz,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_schedules_enabled on schedules(enabled);

drop trigger if exists trg_schedules_updated_at on schedules;
create trigger trg_schedules_updated_at
    before update on schedules
    for each row execute function update_updated_at_column();

-- ============================================================
-- SCRAPE FREQUENCIES (per store/tier config)
-- ============================================================
-- REPLACED: scrape_frequencies with TEXT PK (original used UUID)
CREATE TABLE IF NOT EXISTS scrape_frequencies (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),store_id TEXT REFERENCES stores(id) ON DELETE CASCADE,tier INT,frequency_minutes INT DEFAULT 1440,max_retries INT DEFAULT 2,timeout_seconds INT DEFAULT 30,rate_limit_per_minute INT DEFAULT 10,enabled BOOLEAN DEFAULT TRUE,created_at TIMESTAMPTZ DEFAULT NOW(),updated_at TIMESTAMPTZ DEFAULT NOW());
create index if not exists idx_scrape_freq_store on scrape_frequencies(store_id);
create index if not exists idx_scrape_freq_tier on scrape_frequencies(tier);
create index if not exists idx_scrape_freq_enabled on scrape_frequencies(enabled);

drop trigger if exists trg_scrape_freq_updated_at on scrape_frequencies;
create trigger trg_scrape_freq_updated_at
    before update on scrape_frequencies
    for each row execute function update_updated_at_column();

-- ============================================================
-- ALERT RECIPIENTS (email, telegram, whatsapp)
-- ============================================================
create table if not exists alert_recipients (
    id uuid primary key default gen_random_uuid(),
    channel text not null check (channel in ('email','telegram','whatsapp')),
    target text not null,
    name text,
    active boolean default true,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_alert_recipients_channel on alert_recipients(channel);
create index if not exists idx_alert_recipients_active on alert_recipients(active);

drop trigger if exists trg_alert_recipients_updated_at on alert_recipients;
create trigger trg_alert_recipients_updated_at
    before update on alert_recipients
    for each row execute function update_updated_at_column();

-- ============================================================
-- ALERT RULES (when to notify)
-- ============================================================
create table if not exists alert_rules (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    channel text not null check (channel in ('email','telegram','whatsapp')),
    trigger text not null check (trigger in (
        'price_drop',
        'new_low_price',
        'daily_report',
        'scrape_failure',
        'review_queue_threshold'
    )),
    condition jsonb default '{}',
    frequency_minutes int default 1440,
    recipients uuid[] not null default '{}',
    template text,
    enabled boolean default true,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_alert_rules_trigger on alert_rules(trigger);
create index if not exists idx_alert_rules_enabled on alert_rules(enabled);

drop trigger if exists trg_alert_rules_updated_at on alert_rules;
create trigger trg_alert_rules_updated_at
    before update on alert_rules
    for each row execute function update_updated_at_column();

-- ============================================================
-- FEATURE FLAGS (replace config/features.yaml)
-- ============================================================
create table if not exists feature_flags (
    key text primary key,
    enabled boolean default false,
    description text,
    updated_at timestamptz default now()
);

create index if not exists idx_feature_flags_enabled on feature_flags(enabled);

drop trigger if exists trg_feature_flags_updated_at on feature_flags;
create trigger trg_feature_flags_updated_at
    before update on feature_flags
    for each row execute function update_updated_at_column();

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================
alter table ingredients enable row level security;
alter table stores enable row level security;
alter table schedules enable row level security;
alter table scrape_frequencies enable row level security;
alter table alert_recipients enable row level security;
alter table alert_rules enable row level security;
alter table feature_flags enable row level security;

-- Admin policies (service role has full access via service_client)
create policy "service_role_all" on ingredients for all using (auth.role() = 'service_role');
create policy "service_role_all" on stores for all using (auth.role() = 'service_role');
create policy "service_role_all" on schedules for all using (auth.role() = 'service_role');
create policy "service_role_all" on scrape_frequencies for all using (auth.role() = 'service_role');
create policy "service_role_all" on alert_recipients for all using (auth.role() = 'service_role');
create policy "service_role_all" on alert_rules for all using (auth.role() = 'service_role');
create policy "service_role_all" on feature_flags for all using (auth.role() = 'service_role');

-- Anon read-only for dashboard (adjust as needed)
create policy "anon_read" on ingredients for select using (true);
create policy "anon_read" on stores for select using (true);
create policy "anon_read" on schedules for select using (true);
create policy "anon_read" on scrape_frequencies for select using (true);
create policy "anon_read" on alert_recipients for select using (true);
create policy "anon_read" on alert_rules for select using (true);
create policy "anon_read" on feature_flags for select using (true);

-- ============================================================
-- PHASE 4: Cleanup function (TTL)
-- ============================================================

CREATE OR REPLACE FUNCTION cleanup_old_prices(retention_days int DEFAULT 90)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM price_history WHERE collected_at < now() - (retention_days || ' days')::interval;
    DELETE FROM prices WHERE collected_at < now() - (retention_days || ' days')::interval;
END;
$$;


-- ============================================================
-- PHASE 5: Adapt stores table (add missing 001_config columns)
-- ============================================================
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='scraper') THEN
        ALTER TABLE stores ADD COLUMN scraper text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='url_pattern') THEN
        ALTER TABLE stores ADD COLUMN url_pattern text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='base_url') THEN
        ALTER TABLE stores ADD COLUMN base_url text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='api_endpoint') THEN
        ALTER TABLE stores ADD COLUMN api_endpoint text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='search_url') THEN
        ALTER TABLE stores ADD COLUMN search_url text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='selectors') THEN
        ALTER TABLE stores ADD COLUMN selectors jsonb default '{}';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='publish_day') THEN
        ALTER TABLE stores ADD COLUMN publish_day text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='visit_frequency') THEN
        ALTER TABLE stores ADD COLUMN visit_frequency text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='contact') THEN
        ALTER TABLE stores ADD COLUMN contact text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='priority') THEN
        ALTER TABLE stores ADD COLUMN priority int default 99;
    END IF;
END $$;


-- ============================================================
-- PHASE 6: Add brand column (002_add_brand_column.sql)
-- ============================================================
ALTER TABLE prices ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT '';
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT '';


-- ============================================================
-- PHASE 7: Ensure UNIQUE constraint on prices + price_history
-- (Fix 42P10 error when approving review queue items)
-- ============================================================
-- Remove exact duplicates before adding constraint (keep 1 row per exact match)
DELETE FROM prices p1 USING (
    SELECT ingredient_id, store_id, collected_at, MIN(ctid) AS keep_ctid
    FROM prices
    GROUP BY ingredient_id, store_id, collected_at
    HAVING COUNT(*) > 1
) p2
WHERE p1.ingredient_id = p2.ingredient_id
  AND p1.store_id = p2.store_id
  AND p1.collected_at = p2.collected_at
  AND p1.ctid <> p2.keep_ctid;

DELETE FROM price_history ph1 USING (
    SELECT ingredient_id, store_id, collected_at, MIN(ctid) AS keep_ctid
    FROM price_history
    GROUP BY ingredient_id, store_id, collected_at
    HAVING COUNT(*) > 1
) ph2
WHERE ph1.ingredient_id = ph2.ingredient_id
  AND ph1.store_id = ph2.store_id
  AND ph1.collected_at = ph2.collected_at
  AND ph1.ctid <> ph2.keep_ctid;

-- Drop the old 2-column constraint if it still exists
ALTER TABLE prices DROP CONSTRAINT IF EXISTS prices_ingredient_id_store_id_key;
ALTER TABLE price_history DROP CONSTRAINT IF EXISTS price_history_ingredient_id_store_id_key;

-- Add the 3-column constraint (safe: skip if already exists)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'prices'::regclass
        AND conname = 'prices_ingredient_id_store_id_collected_at_key'
    ) THEN
        ALTER TABLE prices
        ADD CONSTRAINT prices_ingredient_id_store_id_collected_at_key
        UNIQUE (ingredient_id, store_id, collected_at);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'price_history'::regclass
        AND conname = 'price_history_ingredient_id_store_id_collected_at_key'
    ) THEN
        ALTER TABLE price_history
        ADD CONSTRAINT price_history_ingredient_id_store_id_collected_at_key
        UNIQUE (ingredient_id, store_id, collected_at);
    END IF;
END $$;

-- ============================================================
-- PHASE 8: scrape_frequencies indexes + RLS (table already created in Phase 3)
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_scrape_freq_store ON scrape_frequencies(store_id);
CREATE INDEX IF NOT EXISTS idx_scrape_freq_tier ON scrape_frequencies(tier);
CREATE INDEX IF NOT EXISTS idx_scrape_freq_enabled ON scrape_frequencies(enabled);

ALTER TABLE scrape_frequencies ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON scrape_frequencies FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "anon_read" ON scrape_frequencies FOR SELECT USING (true);


-- ============================================================
-- PHASE 9: Add review_queue columns (image_url, source_url, match_reason, match_type)
-- ============================================================
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS image_url TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS source_url TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS match_reason TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS match_type TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS top3 JSONB DEFAULT '[]';


-- ============================================================
-- PHASE 10: Performance indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_prices_ing_collected ON prices(ingredient_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_ing_collected ON price_history(ingredient_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_collected ON review_queue(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_stores_name ON stores(name);
CREATE INDEX IF NOT EXISTS idx_logs_store_started ON scraping_logs(store_name, started_at DESC);


-- ============================================================
-- PHASE 11: Add brands + search_terms to ingredients
-- ============================================================
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS brands TEXT[] DEFAULT '{}';
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS search_terms TEXT[] DEFAULT '{}';


-- ============================================================
-- PHASE 12: Ensure UNIQUE constraint on prices + price_history
-- ============================================================
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'prices'::regclass
        AND conname = 'prices_ingredient_id_store_id_collected_at_key'
    ) THEN
        ALTER TABLE prices
        ADD CONSTRAINT prices_ingredient_id_store_id_collected_at_key
        UNIQUE (ingredient_id, store_id, collected_at);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'price_history'::regclass
        AND conname = 'price_history_ingredient_id_store_id_collected_at_key'
    ) THEN
        ALTER TABLE price_history
        ADD CONSTRAINT price_history_ingredient_id_store_id_collected_at_key
        UNIQUE (ingredient_id, store_id, collected_at);
    END IF;
END $$;


-- ============================================================
-- PHASE 13: RPC upsert_price_rpc — server-side upsert
-- ============================================================
CREATE OR REPLACE FUNCTION upsert_price_rpc(
    p_ingredient_id TEXT,
    p_store_id TEXT,
    p_source TEXT,
    p_store_name TEXT,
    p_raw_product TEXT,
    p_raw_price NUMERIC,
    p_raw_unit TEXT,
    p_collected_at DATE,
    p_valid_from DATE,
    p_valid_until DATE,
    p_validity_raw TEXT,
    p_collected_weekday TEXT,
    p_is_promotion BOOLEAN,
    p_tier INT,
    p_confidence NUMERIC,
    p_normalized JSONB,
    p_city TEXT,
    p_logistics TEXT,
    p_brand TEXT
)
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    INSERT INTO prices (
        ingredient_id, store_id, source, store_name, raw_product,
        raw_price, raw_unit, collected_at, valid_from, valid_until,
        validity_raw, collected_weekday, is_promotion, tier, confidence,
        normalized, city, logistics, brand
    ) VALUES (
        p_ingredient_id, p_store_id, p_source, p_store_name, p_raw_product,
        p_raw_price, p_raw_unit, p_collected_at, p_valid_from, p_valid_until,
        p_validity_raw, p_collected_weekday, p_is_promotion, p_tier, p_confidence,
        p_normalized, p_city, p_logistics, p_brand
    )
    ON CONFLICT (ingredient_id, store_id, collected_at)
    DO UPDATE SET
        source = EXCLUDED.source,
        store_name = EXCLUDED.store_name,
        raw_product = EXCLUDED.raw_product,
        raw_price = EXCLUDED.raw_price,
        raw_unit = EXCLUDED.raw_unit,
        valid_from = EXCLUDED.valid_from,
        valid_until = EXCLUDED.valid_until,
        validity_raw = EXCLUDED.validity_raw,
        collected_weekday = EXCLUDED.collected_weekday,
        is_promotion = EXCLUDED.is_promotion,
        tier = EXCLUDED.tier,
        confidence = EXCLUDED.confidence,
        normalized = EXCLUDED.normalized,
        city = EXCLUDED.city,
        logistics = EXCLUDED.logistics,
        brand = EXCLUDED.brand
    RETURNING to_jsonb(prices.*) INTO result;
    RETURN result;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- ============================================================
-- PHASE 14: recipes + recipe_items tables
-- ============================================================
CREATE TABLE IF NOT EXISTS recipes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    yield_qty INTEGER DEFAULT 40,
    overhead_pct DECIMAL(5,1) DEFAULT 15,
    profit_pct DECIMAL(7,1) DEFAULT 300,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recipe_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recipe_id UUID REFERENCES recipes(id) ON DELETE CASCADE,
    ingredient_id TEXT NOT NULL,
    quantity_g DECIMAL(10,1) DEFAULT 0,
    selected_store TEXT DEFAULT '',
    price_per_kg DECIMAL(10,2) DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_recipe_items_recipe ON recipe_items(recipe_id);

ALTER TABLE recipes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON recipes FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "anon_read" ON recipes FOR SELECT USING (true);

ALTER TABLE recipe_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON recipe_items FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "anon_read" ON recipe_items FOR SELECT USING (true);

-- ============================================================
-- PHASE 15: Insert missing stores (Extra Folheteria, Pao de Acucar Fresh, Dona Dani)
-- ============================================================
INSERT INTO stores (id, name, tier, type, scraper, is_active, city, coverage, collection_method, priority)
VALUES ('extra_folheteria', 'Extra Folheteria', 1, 'extra_flyer', 'extra_flyer_scraper', true, 'Sao Paulo, Santos, Sao Vicente, Praia Grande', 'Campanhas Extra (panificacao/confeitaria) via API HTTP', 'automated', 10)
ON CONFLICT (id) DO NOTHING;

INSERT INTO stores (id, name, tier, type, scraper, is_active, city, coverage, collection_method, priority)
VALUES ('pao_de_acucar_fresh', 'Pao de Acucar Fresh', 1, 'pao_flyer', 'pao_flyer_scraper', true, 'Sao Paulo, Santos, Sao Vicente, Praia Grande', 'Panfletos PA Fresh (panificacao) via API HTTP', 'automated', 10)
ON CONFLICT (id) DO NOTHING;

INSERT INTO stores (id, name, tier, type, scraper, is_active, city, base_url, search_url, selectors, coverage, collection_method, priority)
VALUES ('dona_dani_ingredientes', 'Dona Dani Ingredientes', 2, 'website_catalog', 'website_scraper', true, 'Online - envio nacional', 'https://donadaniingredientes.com.br', 'https://donadaniingredientes.com.br/search/?q={query}', '{"product_card": [".js-item-product", ".item-product", ".col-grid"], "product_name": [".js-item-name", ".item-name"], "product_price": [".js-price-display", ".item-price"]}', '95 SKUs - insumos para panificacao, confeitaria e chocolateria', 'automated', 51)
ON CONFLICT (id) DO NOTHING;

INSERT INTO scrape_frequencies (store_id, tier, frequency_minutes, max_retries, timeout_seconds, rate_limit_per_minute, enabled)
VALUES ('extra_folheteria', 1, 10080, 3, 120, 10, true)
ON CONFLICT DO NOTHING;

INSERT INTO scrape_frequencies (store_id, tier, frequency_minutes, max_retries, timeout_seconds, rate_limit_per_minute, enabled)
VALUES ('pao_de_acucar_fresh', 1, 10080, 3, 120, 10, true)
ON CONFLICT DO NOTHING;

INSERT INTO scrape_frequencies (store_id, tier, frequency_minutes, max_retries, timeout_seconds, rate_limit_per_minute, enabled)
VALUES ('dona_dani_ingredientes', 2, 1440, 3, 120, 10, true)
ON CONFLICT DO NOTHING;


-- ============================================================
-- PHASE 15b: Generated column price_per_kg for server-side sorting
-- ============================================================
ALTER TABLE prices ADD COLUMN IF NOT EXISTS price_per_kg NUMERIC
GENERATED ALWAYS AS ((normalized->>'price_per_kg')::numeric) STORED;

CREATE INDEX IF NOT EXISTS idx_prices_price_per_kg ON prices(price_per_kg)
WHERE price_per_kg IS NOT NULL AND price_per_kg > 0;

ALTER TABLE price_history ADD COLUMN IF NOT EXISTS price_per_kg NUMERIC
GENERATED ALWAYS AS ((normalized->>'price_per_kg')::numeric) STORED;

CREATE INDEX IF NOT EXISTS idx_history_price_per_kg ON price_history(price_per_kg)
WHERE price_per_kg IS NOT NULL AND price_per_kg > 0;


-- ============================================================
-- PHASE 15c: Materialized view for latest prices per ingredient
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS v_latest_prices AS
SELECT DISTINCT ON (ingredient_id, store_id)
    id,
    ingredient_id,
    store_id,
    store_name,
    raw_product,
    raw_price,
    raw_unit,
    normalized,
    price_per_kg,
    collected_at,
    valid_from,
    valid_until,
    is_promotion,
    tier,
    confidence,
    city,
    logistics,
    brand
FROM prices
WHERE valid_from <= CURRENT_DATE
  AND valid_until >= CURRENT_DATE
  AND price_per_kg IS NOT NULL
  AND price_per_kg > 0
ORDER BY ingredient_id, store_id, collected_at DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_v_latest_prices_ing_store
    ON v_latest_prices (ingredient_id, store_id);

CREATE INDEX IF NOT EXISTS idx_v_latest_prices_ingredient
    ON v_latest_prices (ingredient_id);

CREATE INDEX IF NOT EXISTS idx_v_latest_prices_price_kg
    ON v_latest_prices (price_per_kg);


-- ============================================================
-- PHASE 15d: Additional performance indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_prices_store_collected
    ON prices(store_id, collected_at DESC);

CREATE INDEX IF NOT EXISTS idx_prices_promo_collected
    ON prices(collected_at DESC) WHERE is_promotion = TRUE;

CREATE INDEX IF NOT EXISTS idx_review_status_collected
    ON review_queue(status, collected_at DESC);

CREATE INDEX IF NOT EXISTS idx_flyers_store_ocr_collected
    ON flyers(store_name, ocr_status, collected_at DESC);

CREATE INDEX IF NOT EXISTS idx_ingredients_active_name
    ON ingredients(active, canonical_name);


-- ============================================================
-- PHASE 16: Additional cleanup functions
-- ============================================================

-- 1. Cleanup ALL flyers (not just failed OCR) older than retention_days
CREATE OR REPLACE FUNCTION cleanup_old_flyers_all(retention_days int DEFAULT 180)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM flyers WHERE collected_at < now() - (retention_days || ' days')::interval;
END;
$$;

-- Fix review_queue unique constraint
ALTER TABLE review_queue ADD CONSTRAINT review_queue_store_name_raw_product_key UNIQUE (store_name, raw_product);

CREATE OR REPLACE FUNCTION cleanup_resolved_review_items(retention_days int DEFAULT 30)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM review_queue
    WHERE status IN ('approved', 'rejected')
      AND reviewed_at < now() - (retention_days || ' days')::interval;
END;
$$;


-- ============================================================
-- PHASE 17: RPC functions for REST API (port 443) deployment
-- ============================================================

-- 1. exec_sql — executes DDL/any SQL (returns void)
CREATE OR REPLACE FUNCTION exec_sql(sql text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    EXECUTE sql;
END;
$$;

-- 2. exec_sql_query — executes SELECT and returns JSON array
-- Used by tests/conftest.py _SchemaCursor via REST API (porta 443)
CREATE OR REPLACE FUNCTION exec_sql_query(sql text)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSON;
BEGIN
    EXECUTE format('SELECT COALESCE(json_agg(row_to_json(d)), ''[]''::json) FROM (%s) d', sql) INTO result;
    RETURN result;
END;
$$;

-- 3. cleanup_old_logs — TTL for scraping_logs
CREATE OR REPLACE FUNCTION cleanup_old_logs(retention_days int DEFAULT 30)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM scraping_logs WHERE started_at < now() - (retention_days || ' days')::interval;
END;
$$;


-- ============================================================
-- Migration complete. Verify with:
--   SELECT table_name FROM information_schema.tables
--   WHERE table_schema = 'public' ORDER BY table_name;
-- ============================================================