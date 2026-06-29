import pytest
from parsers.normalizer import normalize_price


# All unit patterns from config/ingredients.yaml aliases + real-world store data
@pytest.mark.parametrize(
    "raw_price, raw_unit, expected",
    [
        # ── Basic kg/g units ───────────────────────────────────
        (10.0, "1kg", {"qty": 1, "unit_kg": 1.0, "total_kg": 1.0, "price_per_kg": 10.0, "price_per_un": 10.0}),
        (25.0, "1 kg", {"qty": 1, "unit_kg": 1.0, "total_kg": 1.0, "price_per_kg": 25.0, "price_per_un": 25.0}),
        (5.0, "500g", {"qty": 1, "unit_kg": 0.5, "total_kg": 0.5, "price_per_kg": 10.0, "price_per_un": 5.0}),
        (18.0, "400g", {"qty": 1, "unit_kg": 0.4, "total_kg": 0.4, "price_per_kg": 45.0, "price_per_un": 18.0}),
        (8.0, "350g", {"qty": 1, "unit_kg": 0.35, "total_kg": 0.35, "price_per_kg": 22.86, "price_per_un": 8.0}),
        (6.0, "200g", {"qty": 1, "unit_kg": 0.2, "total_kg": 0.2, "price_per_kg": 30.0, "price_per_un": 6.0}),
        (3.5, "100g", {"qty": 1, "unit_kg": 0.1, "total_kg": 0.1, "price_per_kg": 35.0, "price_per_un": 3.5}),
        (2.0, "30g", {"qty": 1, "unit_kg": 0.03, "total_kg": 0.03, "price_per_kg": 66.67, "price_per_un": 2.0}),
        # ── Caixa/multipack ────────────────────────────────────
        (42.90, "cx 12x395g", {"qty": 12, "unit_kg": 0.395, "total_kg": 4.74, "price_per_kg": 9.05, "price_per_un": 3.58}),
        (15.0, "12un 395g", {"qty": 12, "unit_kg": 0.395, "total_kg": 4.74, "price_per_kg": 3.16, "price_per_un": 1.25}),
        (30.0, "cx com 6x500g", {"qty": 6, "unit_kg": 0.5, "total_kg": 3.0, "price_per_kg": 10.0, "price_per_un": 5.0}),
        (50.0, "pacote com 10x100g", {"qty": 10, "unit_kg": 0.1, "total_kg": 1.0, "price_per_kg": 50.0, "price_per_un": 5.0}),
        (36.0, "cx 24x200g", {"qty": 24, "unit_kg": 0.2, "total_kg": 4.8, "price_per_kg": 7.5, "price_per_un": 1.5}),
        (120.0, "fardo 30x200ml", {"qty": 30, "unit_kg": 0.2, "total_kg": 6.0, "price_per_kg": 20.0, "price_per_un": 4.0}),
        # ── Lata / pote ────────────────────────────────────────
        (20.0, "lata 1kg", {"qty": 1, "unit_kg": 1.0, "total_kg": 1.0, "price_per_kg": 20.0, "price_per_un": 20.0}),
        (8.90, "lata 300g", {"qty": 1, "unit_kg": 0.3, "total_kg": 0.3, "price_per_kg": 29.67, "price_per_un": 8.9}),
        (15.0, "pote 900g", {"qty": 1, "unit_kg": 0.9, "total_kg": 0.9, "price_per_kg": 16.67, "price_per_un": 15.0}),
        # ── Barra ──────────────────────────────────────────────
        (12.0, "barra 500g", {"qty": 1, "unit_kg": 0.5, "total_kg": 0.5, "price_per_kg": 24.0, "price_per_un": 12.0}),
        (8.0, "barra 200g", {"qty": 1, "unit_kg": 0.2, "total_kg": 0.2, "price_per_kg": 40.0, "price_per_un": 8.0}),
        # ── Unidade ────────────────────────────────────────────
        (5.0, "un", None),  # unit-only (sem kg/ml/g) -> camada superior trata
        (10.0, "1un", None),  # 1un (sem kg/ml/g) -> camada superior trata
        (3.0, "pacote", None),  # pacote sem peso -> camada superior trata
        # ── ml / líquidos ──────────────────────────────────────
        (35.0, "30ml", {"qty": 1, "unit_kg": 0.03, "total_kg": 0.03, "price_per_kg": 1166.67, "price_per_un": 35.0}),
        (8.0, "200 ml", {"qty": 1, "unit_kg": 0.2, "total_kg": 0.2, "price_per_kg": 40.0, "price_per_un": 8.0}),
        (6.0, "1l", None),  # so "ml" eh pattern; "l" sozinho retorna None
        # ── Decimal / comma variants ──────────────────────────
        (100.0, "2,5kg", {"qty": 1, "unit_kg": 2.5, "total_kg": 2.5, "price_per_kg": 40.0, "price_per_un": 100.0}),
        (8.50, "0.5kg", {"qty": 1, "unit_kg": 0.5, "total_kg": 0.5, "price_per_kg": 17.0, "price_per_un": 8.5}),
        # ── Edge cases ─────────────────────────────────────────
        (0.0, "1kg", None),
        (-10.0, "1kg", None),
        (10.0, "invalid unit", None),
        (10.0, "", None),
        (10.0, None, None),
    ],
)
def test_normalize_price(raw_price, raw_unit, expected):
    result = normalize_price(raw_price, raw_unit)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert result.to_dict() == expected
