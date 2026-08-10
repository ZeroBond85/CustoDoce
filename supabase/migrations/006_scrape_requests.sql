-- Migration 006: Formalize scrape_requests table
-- This table handles on-demand scraping requests triggered by the Telegram bot.

CREATE TABLE IF NOT EXISTS scrape_requests (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_scrape_requests_status ON scrape_requests(status);
CREATE INDEX IF NOT EXISTS idx_scrape_requests_user ON scrape_requests(user_id);
