-- supabase/009_store_registry.sql
-- Auto-discovered stores registry with dedup ≥92% and review workflow

CREATE TABLE IF NOT EXISTS store_registry (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL,
    normalized_name TEXT        NOT NULL,  -- name stripped to alnum + spaces, upper
    tier            INTEGER     NOT NULL DEFAULT 3,
    type            TEXT        NOT NULL DEFAULT 'manual',
    logistics       TEXT        DEFAULT 'pickup_local',
    city            TEXT        DEFAULT '',
    zone            TEXT        DEFAULT '',
    coverage        TEXT        DEFAULT '',
    collection_method TEXT      DEFAULT 'auto',
    source          TEXT        NOT NULL DEFAULT 'auto',  -- 'yaml' | 'auto' | 'manual'
    status          TEXT        NOT NULL DEFAULT 'pending_review',  -- pending_review | approved | rejected | merged
    match_score     REAL        DEFAULT 0,  -- similarity score vs existing store
    matched_store_id TEXT       REFERENCES stores(id) ON DELETE SET NULL,
    config          JSONB       DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at     TIMESTAMPTZ,
    reviewed_by     TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_store_registry_normalized_name ON store_registry (normalized_name);
CREATE INDEX IF NOT EXISTS idx_store_registry_status ON store_registry (status);
CREATE INDEX IF NOT EXISTS idx_store_registry_source ON store_registry (source);
CREATE INDEX IF NOT EXISTS idx_store_registry_matched_store ON store_registry (matched_store_id);

-- Unique constraint on normalized_name to prevent exact duplicates
CREATE UNIQUE INDEX IF NOT EXISTS uq_store_registry_normalized_name
    ON store_registry (normalized_name)
    WHERE status IN ('pending_review', 'approved');

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_store_registry_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_store_registry_updated_at ON store_registry;
CREATE TRIGGER trg_store_registry_updated_at
    BEFORE UPDATE ON store_registry
    FOR EACH ROW EXECUTE FUNCTION update_store_registry_updated_at();

-- RLS
ALTER TABLE store_registry ENABLE ROW LEVEL SECURITY;

-- Service role full access
CREATE POLICY "service_role_all" ON store_registry
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Anon read only
CREATE POLICY "anon_read" ON store_registry
    FOR SELECT TO anon USING (true);

-- Function to normalize store name (alnum + space, upper)
CREATE OR REPLACE FUNCTION normalize_store_name(raw_name TEXT) RETURNS TEXT LANGUAGE plpgsql AS $$
BEGIN
    RETURN upper(regexp_replace(raw_name, '[^A-Z0-9 ]', '', 'g'));
END;
$$;

-- Helper function to find existing store by name similarity
CREATE OR REPLACE FUNCTION find_similar_store(p_name TEXT, p_threshold REAL DEFAULT 0.92)
RETURNS TABLE (
    id UUID,
    name TEXT,
    similarity REAL
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT s.id, s.name, 
           1 - (levenshtein(lower(normalize_store_name(p_name)), lower(s.name))::REAL / GREATEST(length(normalize_store_name(p_name)), length(s.name))) AS similarity
    FROM stores s
    WHERE s.is_active = true
      AND 1 - (levenshtein(lower(normalize_store_name(p_name)), lower(s.name))::REAL / GREATEST(length(normalize_store_name(p_name)), length(s.name))) >= p_threshold
    ORDER BY similarity DESC
    LIMIT 3;
END;
$$;

-- Function to attempt auto-merge of approved registry entry
CREATE OR REPLACE FUNCTION merge_approved_store(p_registry_id UUID) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    v_registry RECORD;
    v_store_id UUID;
BEGIN
    SELECT * INTO v_registry FROM store_registry WHERE id = p_registry_id AND status = 'approved';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Registry entry not found or not approved: %', p_registry_id;
    END IF;

    -- If already matched to existing store, just mark merged
    IF v_registry.matched_store_id IS NOT NULL THEN
        UPDATE store_registry SET status = 'merged', reviewed_at = now(), reviewed_by = 'auto' WHERE id = p_registry_id;
        RETURN;
    END IF;

    -- Insert new store
    INSERT INTO stores (name, tier, type, logistics, city, zone, coverage, collection_method, config, source)
    VALUES (v_registry.name, v_registry.tier, v_registry.type, v_registry.logistics, 
            v_registry.city, v_registry.zone, v_registry.coverage, v_registry.collection_method,
            v_registry.config, v_registry.source)
    RETURNING id INTO v_store_id;

    UPDATE store_registry 
    SET status = 'merged', 
        matched_store_id = v_store_id,
        reviewed_at = now(),
        reviewed_by = 'auto'
    WHERE id = p_registry_id;
END;
$$;

-- Function to discover new stores from aggregator flyers
CREATE OR REPLACE FUNCTION discover_stores_from_flyers() RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    flyer RECORD;
    norm_name TEXT;
    existing RECORD;
BEGIN
    FOR flyer IN SELECT DISTINCT store_name FROM flyers WHERE store_name IS NOT NULL LOOP
        norm_name := normalize_store_name(flyer.store_name);
        
        -- Check if already in stores
        SELECT INTO existing id FROM stores WHERE normalize_store_name(name) = norm_name AND is_active = true LIMIT 1;
        IF FOUND THEN
            CONTINUE;
        END IF;

        -- Check if already in registry
        SELECT INTO existing id FROM store_registry WHERE normalized_name = norm_name AND status IN ('pending_review', 'approved') LIMIT 1;
        IF FOUND THEN
            CONTINUE;
        END IF;

        -- Insert new registry entry
        INSERT INTO store_registry (name, normalized_name, tier, type, collection_method, source, status, config)
        VALUES (flyer.store_name, norm_name, 3, 'manual', 'auto', 'auto', 'pending_review', '{"source": "flyer_discovery"}')
        ON CONFLICT (normalized_name) WHERE status IN ('pending_review', 'approved') DO NOTHING;
    END LOOP;
END;
$$;