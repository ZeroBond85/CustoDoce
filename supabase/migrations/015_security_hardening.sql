-- ============================================================
-- SECURITY HARDENING (Sprint 2 - Security Audit Fixes)
-- ============================================================

-- 1. Enable RLS on store_units (was missing)
ALTER TABLE public.store_units ENABLE ROW LEVEL SECURITY;

-- Policy: authenticated users can read active store units
CREATE POLICY "store_units_read_active" ON public.store_units
    FOR SELECT
    TO authenticated
    USING (is_active = true);

-- Policy: service role can do everything (for sync scripts)
CREATE POLICY "store_units_service_all" ON public.store_units
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- 2. Fix SECURITY DEFINER functions - add search_path restriction
ALTER FUNCTION public.discover_stores_from_flyers() SET search_path = '';
ALTER FUNCTION public.merge_approved_store() SET search_path = '';

-- 3. Fix permissive policies - replace 'true' with explicit role checks
-- Public read tables: replace 'true' with 'auth.role() IN (''anon'', ''authenticated'')'

DROP POLICY IF EXISTS "anon_read" ON public.alert_recipients;
CREATE POLICY "alert_recipients_read_auth" ON public.alert_recipients
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "anon_read" ON public.alert_rules;
CREATE POLICY "alert_rules_read_auth" ON public.alert_rules
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "anon_read" ON public.feature_flags;
CREATE POLICY "feature_flags_read_auth" ON public.feature_flags
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "Enable read for all users" ON public.flyers;
CREATE POLICY "flyers_read_public" ON public.flyers
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "anon_read" ON public.ingredients;
CREATE POLICY "ingredients_read_public" ON public.ingredients
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "anon_read" ON public.llm_match_cache;
CREATE POLICY "llm_match_cache_read_auth" ON public.llm_match_cache
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "Enable read for all users" ON public.price_history;
CREATE POLICY "price_history_read_public" ON public.price_history
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "Enable read for all users" ON public.prices;
CREATE POLICY "prices_read_public" ON public.prices
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "anon_read" ON public.recipe_items;
CREATE POLICY "recipe_items_read_public" ON public.recipe_items
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "anon_read" ON public.recipes;
CREATE POLICY "recipes_read_public" ON public.recipes
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "Enable read for all users" ON public.review_queue;
CREATE POLICY "review_queue_read_auth" ON public.review_queue
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "anon_read" ON public.schedules;
CREATE POLICY "schedules_read_auth" ON public.schedules
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "anon_read" ON public.scrape_frequencies;
CREATE POLICY "scrape_frequencies_read_auth" ON public.scrape_frequencies
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "anon_read" ON public.scrape_requests;
DROP POLICY IF EXISTS "service_role_all" ON public.scrape_requests;
DROP POLICY IF EXISTS "service_role_delete" ON public.scrape_requests;
CREATE POLICY "scrape_requests_read_auth" ON public.scrape_requests
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "scrape_requests_service_all" ON public.scrape_requests
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "anon_read" ON public.scraper_health_log;
CREATE POLICY "scraper_health_log_read_auth" ON public.scraper_health_log
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "Enable read for all users" ON public.scraping_logs;
CREATE POLICY "scraping_logs_read_auth" ON public.scraping_logs
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "anon_read" ON public.store_registry;
DROP POLICY IF EXISTS "service_role_all" ON public.store_registry;
CREATE POLICY "store_registry_read_public" ON public.store_registry
    FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "store_registry_service_all" ON public.store_registry
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Enable read for all users" ON public.stores;
DROP POLICY IF EXISTS "anon_read" ON public.stores;
CREATE POLICY "stores_read_public" ON public.stores
    FOR SELECT TO anon, authenticated USING (true);

