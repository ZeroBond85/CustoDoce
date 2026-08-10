-- ============================================================
-- OUTLIER DETECTION RPC (for Insights page performance)
-- ============================================================
-- Detects price outliers using z-score > 2 per ingredient
-- Replaces frontend Python loop with DB-side computation
CREATE OR REPLACE FUNCTION detect_price_outliers(p_days INTEGER DEFAULT 90)
RETURNS TABLE (
    ingredient_id TEXT,
    store_name TEXT,
    raw_product TEXT,
    ppk NUMERIC,
    zscore NUMERIC
) LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    RETURN QUERY
    SELECT * FROM (
        WITH stats AS (
            SELECT 
                p.ingredient_id,
                AVG(p.price_per_kg) AS mean_ppk,
                STDDEV(p.price_per_kg) AS std_ppk
            FROM public.prices p
            WHERE p.collected_at >= NOW() - INTERVAL '1 day' * p_days
              AND p.price_per_kg > 0
            GROUP BY p.ingredient_id
            HAVING STDDEV(p.price_per_kg) > 0
        ),
        outliers AS (
            SELECT 
                p.ingredient_id,
                p.store_name,
                p.raw_product,
                p.price_per_kg AS ppk,
                (p.price_per_kg - s.mean_ppk) / s.std_ppk AS zscore
            FROM public.prices p
            JOIN stats s ON p.ingredient_id = s.ingredient_id
            WHERE p.collected_at >= NOW() - INTERVAL '1 day' * p_days
              AND p.price_per_kg > 0
              AND ABS((p.price_per_kg - s.mean_ppk) / s.std_ppk) > 2
        )
        SELECT * FROM outliers
    ) o
    ORDER BY ABS(o.zscore) DESC;
END;
$$;