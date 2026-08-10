-- ============================================================
-- SECURITY: restore anon read for app/dashboard tables (FIX 015)
-- ============================================================
-- Migration 015 narrowed read policies to `authenticated` on tables
-- that the Streamlit dashboard and backend services read via the
-- PUBLIC anon key (get_supabase() prefers SUPABASE_ANON_KEY). This
-- broke anon reads: the dashboard is a private app but has no Supabase
-- Auth JWT flow — all reads go through the anon key.
--
-- Restore read to `anon, authenticated` (public read) while keeping
-- writes service_role-only. The security linter (db_security_lint.py)
-- only flags WRITE policies with USING/WITH CHECK (true) for
-- non-service roles, so public-read SELECT policies are compliant.
--
-- Tables NOT read via anon key (llm_match_cache, scraper_health_log)
-- keep their authenticated-only read policy.

DROP POLICY IF EXISTS "alert_recipients_read_auth" ON public.alert_recipients;
CREATE POLICY "alert_recipients_read_public" ON public.alert_recipients
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "alert_rules_read_auth" ON public.alert_rules;
CREATE POLICY "alert_rules_read_public" ON public.alert_rules
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "feature_flags_read_auth" ON public.feature_flags;
CREATE POLICY "feature_flags_read_public" ON public.feature_flags
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "schedules_read_auth" ON public.schedules;
CREATE POLICY "schedules_read_public" ON public.schedules
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "scrape_frequencies_read_auth" ON public.scrape_frequencies;
CREATE POLICY "scrape_frequencies_read_public" ON public.scrape_frequencies
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "scraping_logs_read_auth" ON public.scraping_logs;
CREATE POLICY "scraping_logs_read_public" ON public.scraping_logs
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "review_queue_read_auth" ON public.review_queue;
CREATE POLICY "review_queue_read_public" ON public.review_queue
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "scrape_requests_read_auth" ON public.scrape_requests;
CREATE POLICY "scrape_requests_read_public" ON public.scrape_requests
    FOR SELECT TO anon, authenticated USING (true);
