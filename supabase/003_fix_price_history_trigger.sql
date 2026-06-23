-- PHASE 15: Fix price_history trigger ON CONFLICT
-- Root cause: trigger trg_price_history did INSERT without ON CONFLICT,
-- causing 23505 when an UPDATE on prices fired the trigger
-- (price_history already had the row from the original INSERT).

CREATE OR REPLACE FUNCTION update_history_from_prices()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO price_history (
        price_id, ingredient_id, store_id, store_name,
        raw_product, raw_price, raw_unit, normalized,
        valid_from, valid_until, validity_raw, collected_weekday, is_promotion,
        collected_at, brand
    ) VALUES (
        NEW.id, NEW.ingredient_id, NEW.store_id, NEW.store_name,
        NEW.raw_product, NEW.raw_price, NEW.raw_unit, NEW.normalized,
        NEW.valid_from, NEW.valid_until, NEW.validity_raw, NEW.collected_weekday, NEW.is_promotion,
        NEW.collected_at, NEW.brand
    )
    ON CONFLICT (ingredient_id, store_id, collected_at)
    DO UPDATE SET
        price_id = EXCLUDED.price_id,
        raw_price = EXCLUDED.raw_price,
        raw_product = EXCLUDED.raw_product,
        raw_unit = EXCLUDED.raw_unit,
        valid_from = EXCLUDED.valid_from,
        valid_until = EXCLUDED.valid_until,
        validity_raw = EXCLUDED.validity_raw,
        is_promotion = EXCLUDED.is_promotion,
        collected_weekday = EXCLUDED.collected_weekday,
        confidence = EXCLUDED.confidence,
        brand = EXCLUDED.brand;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
