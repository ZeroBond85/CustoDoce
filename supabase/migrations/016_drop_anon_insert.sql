-- ============================================================
-- SECURITY: drop anon_insert on scrape_requests (F-01 follow-up)
-- ============================================================
-- The Telegram bot inserts scrape requests via the service_role
-- client (telegram_bot/handlers.py -> get_service_client()), so
-- anon never needs INSERT on scrape_requests. The WITH CHECK (true)
-- policy allowed any anonymous caller to write arbitrary rows.
--
-- Removing it closes the last permissive-write policy for
-- non-service roles (db_security_lint --quick).

DROP POLICY IF EXISTS "anon_insert" ON public.scrape_requests;
