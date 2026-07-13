#!/usr/bin/env python3
"""
CustoDoce — Database Deployment Script

Combines all SQL migrations into a single executable script.
Handles stores table conflict gracefully using DO $$ blocks.

Usage:
    python scripts/deploy_database.py                # Generate consolidated.sql
    python scripts/deploy_database.py --execute       # Execute via Supabase client
    python scripts/deploy_database.py --output FILE   # Write consolidated SQL to FILE
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO_ROOT = Path(__file__).resolve().parent.parent


def generate_consolidated() -> str:
    gen = []

    # ─── 1. seed.sql — Core tables ───────────────────────────────
    gen.append("-- ============================================================")
    gen.append("-- PHASE 1: Core tables (seed.sql)")
    gen.append("-- ============================================================")

    seed_path = REPO_ROOT / "supabase_sql" / "seed.sql"
    if seed_path.exists():
        gen.append(seed_path.read_text(encoding="utf-8"))

    # ─── 2. migration_vigencia.sql — Columns + triggers ──────────
    gen.append("\n-- ============================================================")
    gen.append("-- PHASE 2: Validity/promotion columns (migration_vigencia.sql)")
    gen.append("-- ============================================================")

    vigencia_path = REPO_ROOT / "supabase_sql" / "migration_vigencia.sql"
    if vigencia_path.exists():
        gen.append(vigencia_path.read_text(encoding="utf-8"))

    # ─── 3. 001_config_tables.sql — Config tables (adapted) ────
    gen.append("\n-- ============================================================")
    gen.append("-- PHASE 3: Config tables (001_config_tables.sql, adapted)")
    gen.append("-- ============================================================")

    config_path = REPO_ROOT / "supabase" / "migrations" / "001_config_tables.sql"
    if config_path.exists():
        raw = config_path.read_text(encoding="utf-8")
        lines = raw.split("\n")
        filtered = []
        skip_until_empty = False
        for line in lines:
            s = line.strip().lower()
            # Skip CREATE TABLE IF NOT EXISTS stores (already exists from seed.sql)
            if "create table if not exists stores" in s:
                filtered.append("-- SKIPPED: stores table already exists from seed.sql")
                skip_until_empty = True
                continue
            # Skip CREATE TABLE scrape_frequencies (UUID PK → TEXT PK mismatch)
            # and insert the corrected CREATE TABLE so later Phase 3 refs work
            if "create table if not exists scrape_frequencies" in s:
                filtered.append("-- REPLACED: scrape_frequencies with TEXT PK (original used UUID)")
                filtered.append(
                    "CREATE TABLE IF NOT EXISTS scrape_frequencies ("
                    "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
                    "store_id TEXT REFERENCES stores(id) ON DELETE CASCADE,"
                    "tier INT,"
                    "frequency_minutes INT DEFAULT 1440,"
                    "max_retries INT DEFAULT 2,"
                    "timeout_seconds INT DEFAULT 30,"
                    "rate_limit_per_minute INT DEFAULT 10,"
                    "enabled BOOLEAN DEFAULT TRUE,"
                    "created_at TIMESTAMPTZ DEFAULT NOW(),"
                    "updated_at TIMESTAMPTZ DEFAULT NOW()"
                    ");"
                )
                skip_until_empty = True
                continue
            # End skip when we hit a DDL statement or empty line
            if skip_until_empty:
                if (
                    s == ""
                    or s.startswith("--")
                    or s.startswith("create ")
                    or s.startswith("alter ")
                    or s.startswith("grant ")
                    or s.startswith("drop ")
                ):
                    skip_until_empty = False
                    if not s.startswith("--") and s != "":
                        filtered.append(line)
                continue
            filtered.append(line)

        # Wrap index/trigger on stores(scraper) in safe DO block
        cleaned = "\n".join(filtered)
        cleaned = cleaned.replace(
            "create index if not exists idx_stores_scraper on stores(scraper);",
            "DO $$ BEGIN\n"
            "    IF EXISTS (SELECT 1 FROM information_schema.columns\n"
            "               WHERE table_name='stores' AND column_name='scraper') THEN\n"
            "        CREATE INDEX IF NOT EXISTS idx_stores_scraper ON stores(scraper);\n"
            "    END IF;\n"
            "END $$;",
        )
        gen.append(cleaned)

    # ─── 4. Cleanup function ─────────────────────────────────────
    gen.append("\n-- ============================================================")
    gen.append("-- PHASE 4: Cleanup function (TTL)")
    gen.append("-- ============================================================")
    gen.append("""
CREATE OR REPLACE FUNCTION cleanup_old_prices(retention_days int DEFAULT 90)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM price_history WHERE collected_at < now() - (retention_days || ' days')::interval;
    DELETE FROM prices WHERE collected_at < now() - (retention_days || ' days')::interval;
END;
$$;
""")

    # ─── 5. Add scraper column to stores if missing ──────────────
    gen.append("""
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
""")

    # ─── 6. Add brand column to prices/price_history/review_queue ──
    gen.append("""
-- ============================================================
-- PHASE 6: Add brand column (002_add_brand_column.sql)
-- ============================================================
ALTER TABLE prices ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT '';
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT '';
""")

    gen.append("""
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
""")

    gen.append("""
-- ============================================================
-- PHASE 9: Add review_queue columns (image_url, source_url, match_reason, match_type)
-- ============================================================
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS image_url TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS source_url TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS match_reason TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS match_type TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS top3 JSONB DEFAULT '[]';
""")

    gen.append("""
-- ============================================================
-- PHASE 10: Performance indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_prices_ing_collected ON prices(ingredient_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_ing_collected ON price_history(ingredient_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_collected ON review_queue(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_stores_name ON stores(name);
CREATE INDEX IF NOT EXISTS idx_logs_store_started ON scraping_logs(store_name, started_at DESC);
""")

    gen.append("""
-- ============================================================
-- PHASE 11: Add brands + search_terms to ingredients
-- ============================================================
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS brands TEXT[] DEFAULT '{}';
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS search_terms TEXT[] DEFAULT '{}';
""")

    gen.append("""
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
""")

    gen.append("""
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
""")

    gen.append("""
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
""")

    # ─── PHASE 15b: Generated column price_per_kg + index ──────────────
    gen.append("""
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
""")

    # ─── PHASE 15c: Materialized view v_latest_prices ──────────────────
    gen.append("""
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

ALTER MATERIALIZED VIEW v_latest_prices ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read" ON v_latest_prices FOR SELECT USING (true);
""")

    # ─── PHASE 15d: Additional performance indexes ─────────────────────
    gen.append("""
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
""")

    # ─── PHASE 16: Additional cleanup functions ─────────────────────
    gen.append("""
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

-- 2. Cleanup resolved review_queue items (approved/rejected) older than retention_days
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
""")

    # ─── PHASE 17: RPC functions for REST API deployment ──────────────
    gen.append("""
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
""")

    gen.append("\n-- ============================================================")
    gen.append("-- Migration complete. Verify with:")
    gen.append("--   SELECT table_name FROM information_schema.tables")
    gen.append("--   WHERE table_schema = 'public' ORDER by table_name;")
    gen.append("-- ============================================================")

    gen.append("""
-- ============================================================
-- PHASE 18: Fix review_queue unique constraint
-- ============================================================
-- Remove duplicates before adding constraint
DELETE FROM review_queue rq1 USING (
    SELECT store_name, raw_product, MIN(ctid) AS keep_ctid
    FROM review_queue
    GROUP BY store_name, raw_product
    HAVING COUNT(*) > 1
) rq2
WHERE rq1.store_name = rq2.store_name
  AND rq1.raw_product = rq2.raw_product
  AND rq1.ctid <> rq2.keep_ctid;

ALTER TABLE review_queue ADD CONSTRAINT review_queue_store_name_raw_product_key UNIQUE (store_name, raw_product);
""")
    gen.append("""
-- ============================================================
-- PHASE 19: Final Schema Fixes for Tests
-- ============================================================
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS logistics TEXT;
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE feature_flags ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE scraping_logs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE flyers ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE alert_rules ADD COLUMN IF NOT EXISTS description TEXT;
CREATE INDEX IF NOT EXISTS idx_review_queue_store_product ON review_queue(store_name, raw_product);
CREATE INDEX IF NOT EXISTS idx_alerts_ingredient_store_active ON alert_rules(trigger, enabled);
CREATE INDEX IF NOT EXISTS idx_flyers_store_active ON flyers(store_name, is_active);
""")
    # ─── PHASE 20: LLM Match Cache (004_add_llm_match_cache.sql) ──────────────
    llm_cache_path = REPO_ROOT / "supabase" / "004_add_llm_match_cache.sql"
    if llm_cache_path.exists():
        gen.append("\n-- ============================================================")
        gen.append("-- PHASE 20: LLM Match Cache (004_add_llm_match_cache.sql)")
        gen.append("-- ============================================================")
        gen.append(llm_cache_path.read_text(encoding="utf-8"))

    # ─── PHASE 21: Scraper Health Log (005_add_scraper_health_log.sql) ─────
    health_log_path = REPO_ROOT / "supabase" / "005_add_scraper_health_log.sql"
    if health_log_path.exists():
        gen.append("\n-- ============================================================")
        gen.append("-- PHASE 21: Scraper Health Log (005_add_scraper_health_log.sql)")
        gen.append("-- ============================================================")
        gen.append(health_log_path.read_text(encoding="utf-8"))

    # ─── PHASE 22: RLS fix — service_role-only policies ────────────────
    rls_fix_path = REPO_ROOT / "supabase" / "006_fix_rls_service_role_only.sql"
    if rls_fix_path.exists():
        gen.append("\n-- ============================================================")
        gen.append("-- PHASE 22: RLS fix — service_role-only policies on 6 tables")
        gen.append("-- ============================================================")
        gen.append(rls_fix_path.read_text(encoding="utf-8"))

    # ─── PHASE 23: REVOKE public EXECUTE + SET search_path on RPCs ────
    revoke_path = REPO_ROOT / "supabase" / "007_revoke_exec_functions.sql"
    if revoke_path.exists():
        gen.append("\n-- ============================================================")
        gen.append("-- PHASE 23: REVOKE public EXECUTE + SET search_path on RPCs")
        gen.append("-- ============================================================")
        gen.append(revoke_path.read_text(encoding="utf-8"))

    # ─── PHASE 20: scrape_requests table (formalization) ────────────────
    migration_006_path = REPO_ROOT / "supabase" / "migrations" / "006_scrape_requests.sql"
    if migration_006_path.exists():
        gen.append("\n-- ============================================================")
        gen.append("-- PHASE 20: formalize scrape_requests table (006_scrape_requests.sql)")
        gen.append("-- ============================================================")
        gen.append(migration_006_path.read_text(encoding="utf-8"))

    # ─── PHASE 24: Store Registry + discover_stores_from_flyers (009_store_registry.sql) ──
    store_registry_path = REPO_ROOT / "supabase" / "009_store_registry.sql"
    if store_registry_path.exists():
        gen.append("\n-- ============================================================")
        gen.append("-- PHASE 24: Store Registry table + RPC functions (009_store_registry.sql)")
        gen.append("-- ============================================================")
        gen.append(store_registry_path.read_text(encoding="utf-8"))

    return "\n".join(gen)


def _split_sql_statements(sql: str) -> list[str]:
    """Split SQL by ; respecting dollar-quote $$ ... $$ blocks and string literals.
    Comments (-- and /* */) are skipped entirely — not included in statements."""
    stmts = []
    current = []
    in_dollar = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    while i < len(sql):
        c = sql[i]

        # Line comment -- (skip entirely, do not append to current)
        if not in_dollar and not in_block_comment and c == "-" and i + 1 < len(sql) and sql[i + 1] == "-":
            in_line_comment = True
            i += 2
            continue

        if in_line_comment:
            if c == "\n":
                in_line_comment = False
            i += 1
            continue

        # Block comment /* */ (skip entirely, do not append to current)
        if not in_dollar and c == "/" and i + 1 < len(sql) and sql[i + 1] == "*":
            in_block_comment = True
            i += 2
            continue

        if in_block_comment:
            if c == "*" and i + 1 < len(sql) and sql[i + 1] == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        # Dollar quote start/end (PL/pgSQL $$)
        if c == "$" and i + 1 < len(sql) and sql[i + 1] == "$":
            in_dollar = not in_dollar
            current.append(c)
            i += 1
            continue

        # Semicolon separator (only at top level)
        if c == ";" and not in_dollar and not in_block_comment:
            stmt = "".join(current).strip()
            if stmt:
                stmts.append(stmt)
            current = []
            i += 1
            continue

        current.append(c)
        i += 1

    # Last statement
    stmt = "".join(current).strip()
    if stmt:
        stmts.append(stmt)

    return stmts


def main():
    parser = argparse.ArgumentParser(description="Deploy CustoDoce database schema")
    parser.add_argument("--execute", action="store_true", help="Execute SQL on Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Print SQL plan without executing")
    parser.add_argument("--output", type=str, help="Write consolidated SQL to file")
    args = parser.parse_args()

    sql = generate_consolidated()
    total_tables = 18  # prices, price_history, review_queue, scraping_logs, stores, flyers, ingredients, schedules, scrape_frequencies, alert_recipients, alert_rules, feature_flags, recipes, recipe_items, llm_match_cache, scraper_health_log, scrape_requests, store_registry

    if args.dry_run:
        statements_count = sum(1 for s in sql.split(";") if s.strip())
        head = "\n".join(sql.splitlines()[:40])
        print("DRY-RUN: would execute consolidated SQL against PROD")
        print(f"  Total bytes: {len(sql)} | Statements (by '; ' split): ~{statements_count}")
        print(f"  Expected tables after migration: {total_tables}")
        print("\n--- First 40 lines ---")
        print(head)
        if len(sql.splitlines()) > 40:
            print(f"... [{len(sql.splitlines()) - 40} more lines]")
        return

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(sql, encoding="utf-8")
        print(f"Consolidated SQL written to: {out_path}")
        print(f"Size: {len(sql)} bytes, ~{len(sql.split(chr(10)))} lines")
        print(f"Expected tables after migration: {total_tables}")
        print("\nNext step: Paste the content of this file into Supabase SQL Editor and run.")
        return

    if args.execute:
        print("Executing migrations on Supabase...")
        import psycopg2

        url = os.environ.get("SUPABASE_URL", "")
        if not url:
            print("ERROR: SUPABASE_URL not set")
            sys.exit(1)
        proj = url.split("//")[1].split(".")[0]
        pwd = os.environ.get("SUPABASE_DB_PASSWORD", "")
        if not pwd:
            print("ERROR: SUPABASE_DB_PASSWORD not set (use .env)")
            sys.exit(1)

        conn = None
        for host, port, user in [
            (f"db.{proj}.supabase.co", 5432, "postgres"),
            ("aws-0-us-west-1.pooler.supabase.com", 6543, f"postgres.{proj}"),
        ]:
            try:
                conn = psycopg2.connect(
                    host=host, dbname="postgres", user=user, password=pwd, port=port, connect_timeout=10
                )
                print(f"  Connected to {host}:{port}")
                break
            except Exception as e:
                print(f"  Tried {host}:{port} — {e}")
                continue
        used_rpc = False
        if conn is None:
            print("  Trying Supabase REST API via exec_sql RPC (port 443)...")
            from supabase import create_client

            try:
                anon = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
                sb = create_client(url, anon)
                sb.rpc("exec_sql_query", {"sql": "SELECT 1"}).execute()
                print("  Connected via REST API (port 443)")
                used_rpc = True
                statements = _split_sql_statements(sql)
                ok, fail = 0, 0
                for stmt in statements:
                    stmt = stmt.strip()
                    if not stmt:
                        continue
                    lines = stmt.split("\n")
                    if all(line.strip().startswith("--") for line in lines if line.strip()):
                        continue
                    try:
                        sb.rpc("exec_sql", {"sql": stmt + ";"}).execute()
                        ok += 1
                    except Exception:
                        try:
                            sb.rpc("exec_sql_query", {"sql": stmt + ";"}).execute()
                            ok += 1
                        except Exception as e2:
                            print(f"  WARN ({stmt[:80]}...): {e2}")
                            fail += 1
                print(f"\nMigration via RPC: {ok} OK, {fail} WARN")
                print(f"Expected tables: {total_tables}")
            except Exception as e:
                print(f"  REST API failed: {e}")
                print("ERROR: Cannot connect to Supabase DB on any port or via REST API")
                print("TIP: Paste supabase/consolidated_migration.sql into Supabase SQL Editor")
                sys.exit(1)

        if not used_rpc:
            cur = conn.cursor()
            statements = _split_sql_statements(sql)
            ok, fail = 0, 0
            for stmt in statements:
                stmt = stmt.strip()
                if not stmt:
                    continue
                lines = stmt.split("\n")
                if all(line.strip().startswith("--") for line in lines if line.strip()):
                    continue
                try:
                    cur.execute(stmt + ";")
                    conn.commit()
                    ok += 1
                except Exception as e:
                    conn.rollback()
                    err = str(e)[:120]
                    print(f"  WARN: {err}")
                    fail += 1
            cur.close()
            conn.close()
            print(f"\nMigration complete: {ok} OK, {fail} WARN")
            print(f"Expected tables: {total_tables}")

        # --- Post-deploy: ensure trigger function has ON CONFLICT ---
        from supabase import create_client

        try:
            anon = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            sb = create_client(url, anon)
            trigger_sql = """
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
        collected_weekday = EXCLUDED.collected_weekday;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
            sb.rpc("exec_sql", {"sql": trigger_sql}).execute()
            print("  Trigger function verified via REST API")
        except Exception as e:
            print(f"  WARN: could not verify trigger via REST API: {e}")

        print("\nMigration complete.")
        return

    # Default: print to stdout
    print(sql)


if __name__ == "__main__":
    main()
