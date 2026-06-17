-- CustoDoce — Migration: Vigência, Promoção e Weekday
-- Executar no Supabase SQL Editor após seed.sql

-- ============================================================================
-- PRICES: add new columns (safe: IF NOT EXISTS)
-- ============================================================================
ALTER TABLE prices ADD COLUMN IF NOT EXISTS valid_from DATE DEFAULT CURRENT_DATE;
ALTER TABLE prices ADD COLUMN IF NOT EXISTS validity_raw TEXT DEFAULT '';
ALTER TABLE prices ADD COLUMN IF NOT EXISTS collected_weekday TEXT DEFAULT '';
ALTER TABLE prices ADD COLUMN IF NOT EXISTS is_promotion BOOLEAN DEFAULT FALSE;

-- Update existing rows: valid_until default +7 dias if NULL
UPDATE prices SET valid_until = collected_at::DATE + INTERVAL '7 days' WHERE valid_until IS NULL;
ALTER TABLE prices ALTER COLUMN valid_until SET DEFAULT (CURRENT_DATE + INTERVAL '7 days');

-- ============================================================================
-- PRICE HISTORY: add new columns
-- ============================================================================
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS valid_from DATE DEFAULT CURRENT_DATE;
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS valid_until DATE DEFAULT (CURRENT_DATE + INTERVAL '7 days');
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS validity_raw TEXT DEFAULT '';
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS collected_weekday TEXT DEFAULT '';
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS is_promotion BOOLEAN DEFAULT FALSE;

-- ============================================================================
-- REVIEW QUEUE: add validity_raw
-- ============================================================================
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS validity_raw TEXT DEFAULT '';

-- ============================================================================
-- FLYERS: add valid_from, valid_until
-- ============================================================================
ALTER TABLE flyers ADD COLUMN IF NOT EXISTS valid_from DATE;
ALTER TABLE flyers ADD COLUMN IF NOT EXISTS valid_until DATE;

-- ============================================================================
-- INDEXES for new columns
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_prices_valid_from ON prices(valid_from);
CREATE INDEX IF NOT EXISTS idx_prices_valid_until ON prices(valid_until);
CREATE INDEX IF NOT EXISTS idx_prices_promotion ON prices(is_promotion) WHERE is_promotion = TRUE;
CREATE INDEX IF NOT EXISTS idx_prices_weekday ON prices(collected_weekday);
CREATE INDEX IF NOT EXISTS idx_history_valid_until ON price_history(valid_until);
CREATE INDEX IF NOT EXISTS idx_history_promotion ON price_history(is_promotion) WHERE is_promotion = TRUE;

-- ============================================================================
-- UPDATE trigger to include new columns
-- ============================================================================
CREATE OR REPLACE FUNCTION update_history_from_prices()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO price_history (
        price_id, ingredient_id, store_id, store_name,
        raw_product, raw_price, raw_unit, normalized,
        valid_from, valid_until, validity_raw, collected_weekday, is_promotion,
        collected_at
    ) VALUES (
        NEW.id, NEW.ingredient_id, NEW.store_id, NEW.store_name,
        NEW.raw_product, NEW.raw_price, NEW.raw_unit, NEW.normalized,
        NEW.valid_from, NEW.valid_until, NEW.validity_raw, NEW.collected_weekday, NEW.is_promotion,
        NEW.collected_at
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Update UNIQUE constraint to include collected_at
-- ============================================================================
-- Drop old unique and recreate with collected_at
ALTER TABLE prices DROP CONSTRAINT IF EXISTS prices_ingredient_id_store_id_key;
ALTER TABLE prices ADD CONSTRAINT prices_ingredient_id_store_id_collected_at_key UNIQUE (ingredient_id, store_id, collected_at);
