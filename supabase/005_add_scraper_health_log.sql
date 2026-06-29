-- ============================================================
-- PHASE S4 (Sprint 4): Scraper Health Log — Self-Healing Tracking
-- Auto-disable / re-activation history per scraper. Required by
-- AGENTS.md Lição #15 (self-healing obrigatório). Consumed by
-- services/scraper_health.py + scripts/heal_scrapers.py + cron
-- .github/workflows/heal-scrapers.yml (every 15 days).
-- ============================================================

CREATE TABLE IF NOT EXISTS scraper_health_log (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    scraper_name    TEXT         NOT NULL,
    -- Lifecycle event types
    event_type      TEXT         NOT NULL CHECK (event_type IN (
        'failure',
        'success',
        'auto_disabled',
        'auto_reactivated',
        'heal_attempt',
        'heal_success',
        'heal_failure',
        'manual_disable',
        'manual_reactivate'
    )),
    -- Per-event context (snapshot at event time)
    failures_count  INT          NOT NULL DEFAULT 0,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    reason          TEXT,
    items_found     INT,
    products_matched INT,
    flyer_count     INT,
    error_class     TEXT,        -- e.g. ClientError, LayoutChanged, Timeout
    attempted_by    TEXT,        -- 'auto' | 'manual:<username>' | 'cron'
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Indices for fast lookup
CREATE INDEX IF NOT EXISTS idx_scraper_health_log_name
    ON scraper_health_log(scraper_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scraper_health_log_event
    ON scraper_health_log(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scraper_health_log_active_failures
    ON scraper_health_log(scraper_name, event_type)
    WHERE event_type = 'failure';

-- Trigger: updated helper for row-level bookkeeping (none today; reserved).
-- Cleanup function: deletes log rows older than retention (default 180d).
CREATE OR REPLACE FUNCTION cleanup_scraper_health_log(retention_days int DEFAULT 180)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM scraper_health_log
    WHERE created_at < now() - (retention_days || ' days')::interval;
END;
$$;

-- Row-Level Security: anon read for transparency, service_role writes.
ALTER TABLE scraper_health_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON scraper_health_log
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "anon_read" ON scraper_health_log
    FOR SELECT USING (true);

COMMENT ON TABLE  scraper_health_log IS
    'Lifecycle log per scraper: failures, auto-disable, heal attempts. Drives services/scraper_health.py + cron .github/workflows/heal-scrapers.yml every 15d. See AGENTS.md Lição #15.';
COMMENT ON COLUMN scraper_health_log.event_type IS
    'failure | success | auto_disabled | auto_reactivated | heal_attempt | heal_success | heal_failure | manual_disable | manual_reactivate';
COMMENT ON COLUMN scraper_health_log.failures_count IS
    'Cumulative consecutive failures at the moment of the event.';
COMMENT ON COLUMN scraper_health_log.error_class IS
    'Free-form class hint (e.g. ClientError, LayoutChanged, Timeout) used by services.scraper_health.classify_error_for_alert().';
COMMENT ON COLUMN scraper_health_log.attempted_by IS
    'auto (cron + policy) | manual:<user> (Lojas tab CRUD) | cron (CI workflow).';
