-- Migration 011: Enable RLS on scrape_requests (security audit F-01)
-- The Telegram bot inserts rows via the anon key (public API key), so anon
-- needs INSERT + SELECT on its own rows. All administrative mutations go
-- through the service_role client (bypasses RLS).
-- Reference: security audit walkthrough, finding F-01 (Critical).

ALTER TABLE scrape_requests ENABLE ROW LEVEL SECURITY;

-- service_role has full control (used by backend scripts / Telegram bot server-side)
DROP POLICY IF EXISTS "service_role_all" ON scrape_requests;
CREATE POLICY "service_role_all"
    ON scrape_requests
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- anon can insert a scrape request (Telegram bot uses the public anon key)
DROP POLICY IF EXISTS "anon_insert" ON scrape_requests;
CREATE POLICY "anon_insert"
    ON scrape_requests
    FOR INSERT
    TO anon
    WITH CHECK (true);

-- anon can read scrape request status (no sensitive write path exposed)
DROP POLICY IF EXISTS "anon_read" ON scrape_requests;
CREATE POLICY "anon_read"
    ON scrape_requests
    FOR SELECT
    TO anon
    USING (true);

-- Explicit DELETE policy for service_role (defense-in-depth; FOR ALL above
-- already covers it, this documents intent and scopes it to service_role).
DROP POLICY IF EXISTS "service_role_delete" ON scrape_requests;
CREATE POLICY "service_role_delete"
    ON scrape_requests
    FOR DELETE
    TO service_role
    USING (true);

-- F-05: ensure cleanup/utility functions are NOT callable by anon/authenticated
-- via PostgREST RPC. They are plain functions (not SECURITY DEFINER) and are not
-- granted by default, but we revoke explicitly to be safe.
REVOKE ALL ON FUNCTION cleanup_old_prices(int) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION cleanup_old_flyers_all(int) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION cleanup_resolved_review_items(int) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION cleanup_old_logs(int) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION cleanup_old_llm_cache(int) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION cleanup_scraper_health_log(int) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION cleanup_old_prices(int) TO service_role;
GRANT EXECUTE ON FUNCTION cleanup_old_flyers_all(int) TO service_role;
GRANT EXECUTE ON FUNCTION cleanup_resolved_review_items(int) TO service_role;
GRANT EXECUTE ON FUNCTION cleanup_old_logs(int) TO service_role;
GRANT EXECUTE ON FUNCTION cleanup_old_llm_cache(int) TO service_role;
GRANT EXECUTE ON FUNCTION cleanup_scraper_health_log(int) TO service_role;
