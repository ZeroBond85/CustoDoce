"""Consumer tests: MOCK_PRICES / MOCK_LATEST_PRICES drive real normalization + brand extraction.

Garante que os mocks centralizados em tests/unit/fixtures/mock_data.py são
efetivamente usados por lógica de produção (não só validados estruturalmente).
"""

from __future__ import annotations

from parsers import normalizer
from parsers.brand_extractor import extract_brand
from tests.unit.fixtures.mock_data import MOCK_INGREDIENTS, MOCK_LATEST_PRICES, MOCK_PRICES


def test_mock_prices_normalize_matches_stored_price_per_kg():
    for price in MOCK_PRICES:
        raw_price = float(price["raw_price"])
        raw_unit = price["raw_unit"]
        result = normalizer.normalize_price(raw_price, raw_unit)
        assert result is not None, f"normalize_price falhou para {price['raw_product']}"
        stored = price["normalized"]
        assert abs(result.price_per_kg - stored["price_per_kg"]) < 0.05
        assert abs(result.unit_kg - stored["unit_kg"]) < 1e-6
        assert abs(result.total_kg - stored["total_kg"]) < 1e-6
        assert result.qty == stored["qty"]


def test_mock_latest_prices_normalize_consistent():
    for price in MOCK_LATEST_PRICES:
        result = normalizer.normalize_price(float(price["raw_price"]), price["raw_unit"])
        assert result is not None
        assert abs(result.price_per_kg - price["price_per_kg"]) < 0.05


def test_mock_prices_brand_extraction():
    assai = next(p for p in MOCK_PRICES if p["id"] == "price-001")
    brand = extract_brand(assai["raw_product"], MOCK_INGREDIENTS[0])
    assert brand == "Moça"


def test_mock_prices_price_per_un_equals_raw_when_qty_one():
    for price in MOCK_PRICES:
        result = normalizer.normalize_price(float(price["raw_price"]), price["raw_unit"])
        assert result is not None
        if result.qty == 1:
            assert abs(result.price_per_un - float(price["raw_price"])) < 1e-6
