import pytest
from parsers.normalizer import normalize_price


@pytest.mark.parametrize(
    "raw_price, raw_unit, expected",
    [
        # Basic cases
        (10.0, "1kg", {"qty": 1, "unit_kg": 1.0, "total_kg": 1.0, "price_per_kg": 10.0, "price_per_un": 10.0}),
        (5.0, "500g", {"qty": 1, "unit_kg": 0.5, "total_kg": 0.5, "price_per_kg": 10.0, "price_per_un": 5.0}),
        (
            42.90,
            "cx 12x395g",
            {"qty": 12, "unit_kg": 0.395, "total_kg": 4.74, "price_per_kg": 9.05, "price_per_un": 3.58},
        ),
        (
            15.0,
            "12un 395g",
            {"qty": 12, "unit_kg": 0.395, "total_kg": 4.74, "price_per_kg": 3.16, "price_per_un": 1.25},
        ),
        (20.0, "lata 1kg", {"qty": 1, "unit_kg": 1.0, "total_kg": 1.0, "price_per_kg": 20.0, "price_per_un": 20.0}),
        # Variant units and formats
        (100.0, "2,5kg", {"qty": 1, "unit_kg": 2.5, "total_kg": 2.5, "price_per_kg": 40.0, "price_per_un": 100.0}),
        (8.0, "200 ml", {"qty": 1, "unit_kg": 0.2, "total_kg": 0.2, "price_per_kg": 40.0, "price_per_un": 8.0}),
        (
            50.0,
            "pacote com 10x100g",
            {"qty": 10, "unit_kg": 0.1, "total_kg": 1.0, "price_per_kg": 50.0, "price_per_un": 5.0},
        ),
        (30.0, "cx com 6x500g", {"qty": 6, "unit_kg": 0.5, "total_kg": 3.0, "price_per_kg": 10.0, "price_per_un": 5.0}),
        # Edge cases
        (0.0, "1kg", None),
        (-10.0, "1kg", None),
        (10.0, "invalid unit", None),
    ],
)
def test_normalize_price(raw_price, raw_unit, expected):
    result = normalize_price(raw_price, raw_unit)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        # Using to_dict() for easy comparison of rounded values
        assert result.to_dict() == expected
