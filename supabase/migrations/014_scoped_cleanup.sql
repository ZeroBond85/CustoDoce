-- ============================================================
-- SCOPED CLEANUP FUNCTIONS (for safe integration tests)
-- ============================================================
-- Root cause: test_cleanup_* chamava cleanup_old_prices/logs/flyers
-- GLOBALMENTE no DB de producao (CI roda integration com SERVICE_ROLE_KEY
-- em todo PR), varrendo dados reais com collected_at < retention.
--
-- Fix: adicionar parametro opcional store_id_filter / store_name_filter.
-- Quando NULL (default), comportamento global (uso em producao).
-- Quando informado, afeta apenas rows daquele store (uso em testes).
CREATE OR REPLACE FUNCTION cleanup_old_prices(
    retention_days int DEFAULT 90,
    store_id_filter text DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM price_history
     WHERE collected_at < now() - (retention_days || ' days')::interval
       AND (store_id_filter IS NULL OR store_id = store_id_filter);
    DELETE FROM prices
     WHERE collected_at < now() - (retention_days || ' days')::interval
       AND (store_id_filter IS NULL OR store_id = store_id_filter);
END;
$$;


CREATE OR REPLACE FUNCTION cleanup_old_logs(
    retention_days int DEFAULT 30,
    store_name_filter text DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM scraping_logs
     WHERE started_at < now() - (retention_days || ' days')::interval
       AND (store_name_filter IS NULL OR store_name = store_name_filter);
END;
$$;


CREATE OR REPLACE FUNCTION cleanup_old_flyers_all(
    retention_days int DEFAULT 180,
    store_name_filter text DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM flyers
     WHERE collected_at < now() - (retention_days || ' days')::interval
       AND (store_name_filter IS NULL OR store_name = store_name_filter);
END;
$$;
