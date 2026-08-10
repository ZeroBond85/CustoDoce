-- Migration 007: Portal store fluidity
-- Makes DB the single source of truth for stores: every new/updated store
-- automatically gets a scrape_frequencies row (opt-in barrier preserved),
-- and tracks provenance (yaml seed vs portal edit) so the YAML sync never
-- silently overwrites a portal-owned store.
--
-- Idempotent: safe to re-run. Works on both the legacy 001 schema
-- (stores.id UUID, name UNIQUE) and the consolidated schema (stores.id TEXT).

-- ─── 1. Provenance column ─────────────────────────────────────
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'stores' AND column_name = 'source'
    ) THEN
        ALTER TABLE stores ADD COLUMN source text NOT NULL DEFAULT 'yaml'
            CHECK (source IN ('yaml', 'portal'));
    END IF;
END $$;

-- ─── 2. UNIQUE(name) (audited: zero duplicates at deploy time) ──
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'stores'::regclass AND contype = 'u'
          AND conname = 'stores_name_unique'
    ) THEN
        ALTER TABLE stores ADD CONSTRAINT stores_name_unique UNIQUE (name);
    END IF;
END $$;

-- ─── 3. Default frequency by tier ──────────────────────────────
CREATE OR REPLACE FUNCTION default_scrape_frequency_minutes(p_tier int)
RETURNS int LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE p_tier
        WHEN 1 THEN 10080   -- semanal
        WHEN 2 THEN 1440    -- diária
        WHEN 3 THEN 1440    -- diária
        WHEN 4 THEN 43200   -- mensal
        ELSE 1440
    END;
$$;

-- ─── 4. Keep scrape_frequencies in sync with stores ───────────
CREATE OR REPLACE FUNCTION maintain_scrape_frequency()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO scrape_frequencies (
            store_id, tier, frequency_minutes, max_retries,
            timeout_seconds, rate_limit_per_minute, enabled
        ) VALUES (
            NEW.id, NEW.tier, default_scrape_frequency_minutes(NEW.tier),
            3, 120, 10, NEW.active
        )
        ON CONFLICT (store_id) DO UPDATE SET
            tier = EXCLUDED.tier,
            frequency_minutes = EXCLUDED.frequency_minutes,
            enabled = EXCLUDED.enabled,
            updated_at = now();
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        IF (OLD.tier IS DISTINCT FROM NEW.tier)
           OR (OLD.active IS DISTINCT FROM NEW.active) THEN
            INSERT INTO scrape_frequencies (
                store_id, tier, frequency_minutes, max_retries,
                timeout_seconds, rate_limit_per_minute, enabled
            ) VALUES (
                NEW.id, NEW.tier, default_scrape_frequency_minutes(NEW.tier),
                3, 120, 10, NEW.active
            )
            ON CONFLICT (store_id) DO UPDATE SET
                tier = EXCLUDED.tier,
                frequency_minutes = EXCLUDED.frequency_minutes,
                enabled = EXCLUDED.enabled,
                updated_at = now();
        END IF;
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_maintain_scrape_frequency ON stores;
CREATE TRIGGER trg_maintain_scrape_frequency
    AFTER INSERT OR UPDATE OF tier, active ON stores
    FOR EACH ROW EXECUTE FUNCTION maintain_scrape_frequency();

-- ─── 5. Backfill: ensure every existing active store has a row ──
INSERT INTO scrape_frequencies (
    store_id, tier, frequency_minutes, max_retries,
    timeout_seconds, rate_limit_per_minute, enabled
)
SELECT
    s.id AS store_id, s.tier, default_scrape_frequency_minutes(s.tier) AS frequency_minutes,
    3 AS max_retries, 120 AS timeout_seconds, 10 AS rate_limit_per_minute, s.active AS enabled
FROM stores AS s
WHERE NOT EXISTS (
    SELECT 1 FROM scrape_frequencies AS sf WHERE sf.store_id = s.id
);
