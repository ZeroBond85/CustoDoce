-- PHASE 26: Store addresses, units, and address extraction from flyers
-- Adds address columns to stores/flyers/store_registry, creates store_units table,
-- and updates merge_approved_store RPC to handle address data.

-- 1. Add address columns to stores
ALTER TABLE stores ADD COLUMN IF NOT EXISTS address TEXT DEFAULT '';
ALTER TABLE stores ADD COLUMN IF NOT EXISTS neighborhood TEXT DEFAULT '';
ALTER TABLE stores ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT '';
ALTER TABLE stores ADD COLUMN IF NOT EXISTS latitude DECIMAL(10,7);
ALTER TABLE stores ADD COLUMN IF NOT EXISTS longitude DECIMAL(10,7);

-- 2. Create store_units table for multi-unit stores (e.g., Assaí has 5 units)
CREATE TABLE IF NOT EXISTS store_units (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    unit_name TEXT DEFAULT '',
    address TEXT DEFAULT '',
    neighborhood TEXT DEFAULT '',
    city TEXT DEFAULT '',
    state TEXT DEFAULT 'SP',
    zipcode TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    latitude DECIMAL(10,7),
    longitude DECIMAL(10,7),
    source TEXT NOT NULL DEFAULT 'auto',
    confidence DECIMAL(3,2) DEFAULT 1.0,
    is_active BOOLEAN DEFAULT TRUE,
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (store_id, address)
);

-- 3. Add address columns to flyers (for address extracted via OCR)
ALTER TABLE flyers ADD COLUMN IF NOT EXISTS address TEXT DEFAULT '';
ALTER TABLE flyers ADD COLUMN IF NOT EXISTS address_confidence DECIMAL(3,2) DEFAULT 0;

-- 4. Add address columns to store_registry (for store discovery with location)
ALTER TABLE store_registry ADD COLUMN IF NOT EXISTS address TEXT DEFAULT '';
ALTER TABLE store_registry ADD COLUMN IF NOT EXISTS neighborhood TEXT DEFAULT '';
ALTER TABLE store_registry ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT '';
ALTER TABLE store_registry ADD COLUMN IF NOT EXISTS address_confidence DECIMAL(3,2) DEFAULT 0;
ALTER TABLE store_registry ADD COLUMN IF NOT EXISTS discovery_source TEXT DEFAULT 'flyer';
ALTER TABLE store_registry ADD COLUMN IF NOT EXISTS region TEXT DEFAULT '';

-- 5. Update merge_approved_store RPC to copy address data
CREATE OR REPLACE FUNCTION merge_approved_store(p_registry_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_registry RECORD;
    v_store_id TEXT;
BEGIN
    SELECT * INTO v_registry
    FROM store_registry
    WHERE id = p_registry_id AND status = 'approved';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Registry entry not found or not approved: %', p_registry_id;
    END IF;

    -- If already matched to existing store, just mark merged and update address
    IF v_registry.matched_store_id IS NOT NULL THEN
        UPDATE stores
        SET address = COALESCE(NULLIF(v_registry.address, ''), stores.address),
            neighborhood = COALESCE(NULLIF(v_registry.neighborhood, ''), stores.neighborhood),
            phone = COALESCE(NULLIF(v_registry.phone, ''), stores.phone)
        WHERE id = v_registry.matched_store_id;
        UPDATE store_registry
        SET status = 'merged', updated_at = now()
        WHERE id = p_registry_id;
        RETURN;
    END IF;

    -- Insert new store with address data
    INSERT INTO stores (
        name, tier, type, logistics, city, zone, coverage,
        collection_method, address, neighborhood, phone,
        config, source
    ) VALUES (
        v_registry.name, v_registry.tier, v_registry.type,
        v_registry.logistics, v_registry.city, v_registry.zone,
        v_registry.coverage, v_registry.collection_method,
        v_registry.address, v_registry.neighborhood, v_registry.phone,
        v_registry.config, v_registry.source
    )
    RETURNING id INTO v_store_id;

    UPDATE store_registry
    SET status = 'merged', matched_store_id = v_store_id, updated_at = now()
    WHERE id = p_registry_id;
END;
$$;

-- 6. Update discover_stores_from_flyers RPC to include address fields
CREATE OR REPLACE FUNCTION discover_stores_from_flyers()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO store_registry (
        name, normalized_name, tier, type, logistics,
        city, coverage, collection_method, source, status,
        region
    )
    SELECT DISTINCT
        f.store_name,
        upper(regexp_replace(f.store_name, '[^A-Z0-9 ]', '', 'g')),
        3,
        'manual',
        'pickup_local',
        f.city,
        f.region,
        'auto',
        'auto',
        'pending_review',
        f.region
    FROM flyers f
    WHERE NOT EXISTS (
        SELECT 1 FROM stores s
        WHERE upper(regexp_replace(s.name, '[^A-Z0-9 ]', '', 'g'))
            = upper(regexp_replace(f.store_name, '[^A-Z0-9 ]', '', 'g'))
    )
    AND NOT EXISTS (
        SELECT 1 FROM store_registry r
        WHERE r.status IN ('pending_review', 'approved')
        AND r.normalized_name
            = upper(regexp_replace(f.store_name, '[^A-Z0-9 ]', '', 'g'))
    )
    AND f.store_name IS NOT NULL
    AND f.store_name != '';
END;
$$;
