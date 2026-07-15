-- PHASE 25: enforce 1 row per store_id in scrape_frequencies
-- Root cause: upsert_scrape_frequency() used a plain upsert without on_conflict,
-- so every write created a new UUID row -> 424 duplicate rows accumulated
-- (494 total vs 70 stores). Duplicates make load_stores() last-write-wins and
-- break the PostgREST 1000-row cap in join tests.
-- Fix: unique index on store_id + dedup of existing rows (already applied in prod).

CREATE UNIQUE INDEX IF NOT EXISTS uq_scrape_frequencies_store_id
    ON scrape_frequencies (store_id);
