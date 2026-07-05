-- ============================================================
-- Migration 007: REVOKE public EXECUTE + SET search_path on RPCs
--
-- Problem: exec_sql, exec_sql_query, upsert_price_rpc are
-- SECURITY DEFINER without SET search_path. Any user holding
-- the anon key can call them (no REVOKE on public schema).
-- Without SET search_path, search_path injection can hijack
-- these functions (SB-013).
--
-- Fix: REVOKE public access, GRANT only to service_role,
-- and pin search_path to 'public' on all 3 RPCs.
-- ============================================================

-- ============================================================
-- 1. exec_sql
-- ============================================================
CREATE OR REPLACE FUNCTION exec_sql(sql text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
BEGIN
    EXECUTE sql;
END;
$$;

REVOKE ALL ON FUNCTION exec_sql(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION exec_sql(text) TO service_role;

-- ============================================================
-- 2. exec_sql_query
-- ============================================================
CREATE OR REPLACE FUNCTION exec_sql_query(sql text)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
DECLARE
    result JSON;
BEGIN
    EXECUTE format('SELECT COALESCE(json_agg(row_to_json(d)), ''[]''::json) FROM (%s) d', sql) INTO result;
    RETURN result;
END;
$$;

REVOKE ALL ON FUNCTION exec_sql_query(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION exec_sql_query(text) TO service_role;

-- ============================================================
-- 3. upsert_price_rpc
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
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
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
$$;

REVOKE ALL ON FUNCTION upsert_price_rpc(
    TEXT, TEXT, TEXT, TEXT, TEXT, NUMERIC, TEXT, DATE,
    DATE, DATE, TEXT, TEXT, BOOLEAN, INT, NUMERIC, JSONB, TEXT, TEXT, TEXT
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION upsert_price_rpc(
    TEXT, TEXT, TEXT, TEXT, TEXT, NUMERIC, TEXT, DATE,
    DATE, DATE, TEXT, TEXT, BOOLEAN, INT, NUMERIC, JSONB, TEXT, TEXT, TEXT
) TO service_role;
