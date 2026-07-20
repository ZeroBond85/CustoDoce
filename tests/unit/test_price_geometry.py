"""Tests for geometric price reconstruction from flyer OCR regions.

Two layers:
  * deterministic synthetic tests (hand-built boxes) for exact assertions;
  * aggregate property tests against a trimmed real-encarte OCR fixture
    (Tenda), validating plausibility without needing the source image.
"""
import json
from pathlib import Path

import pytest

from parsers.price_geometry import (
    Price,
    deduplicate_dual_prices,
    is_boilerplate,
    is_product_name,
    reconstruct_prices,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "flyer_ocr_sample.json"

# Plausible centavo endings for Brazilian supermarket pricing.
_PLAUSIBLE_CENTS = {0, 5, 6, 7, 8, 9, 19, 29, 39, 49, 50, 59, 66, 69, 79, 89, 90, 99}


def _box(cx: float, cy: float, w: float, h: float):
    """Build a 4-point OCR box centered at (cx, cy)."""
    return [
        [cx - w / 2, cy - h / 2],
        [cx + w / 2, cy - h / 2],
        [cx + w / 2, cy + h / 2],
        [cx - w / 2, cy + h / 2],
    ]


def _region(text, cx, cy, w, h, score=1.0):
    return {"text": text, "box": _box(cx, cy, w, h), "score": score}


# --------------------------------------------------------------------------
# Deterministic synthetic tests
# --------------------------------------------------------------------------


def test_reais_plus_superscript_cents_merge():
    """Tall '33' + small '90' to the upper-right -> 33.90."""
    regions = [
        _region("33", cx=1888, cy=639, w=60, h=77),
        _region("90", cx=1939, cy=631, w=40, h=47),
    ]
    prices = reconstruct_prices(regions)
    assert len(prices) == 1
    assert prices[0].value == pytest.approx(33.90)


def test_four_digit_blob_split():
    regions = [_region("3590", cx=427, cy=1111, w=180, h=139)]
    prices = reconstruct_prices(regions)
    assert prices[0].value == pytest.approx(35.90)


def test_three_digit_blob_split():
    regions = [_region("280", cx=934, cy=644, w=120, h=101)]
    prices = reconstruct_prices(regions)
    assert prices[0].value == pytest.approx(2.80)


@pytest.mark.parametrize("text,expected", [("43,50", 43.50), ("43.50", 43.50), ("R$ 19,90", 19.90)])
def test_explicit_separator(text, expected):
    regions = [_region(text, cx=100, cy=100, w=120, h=90)]
    prices = reconstruct_prices(regions)
    assert prices[0].value == pytest.approx(expected)


@pytest.mark.parametrize(
    "text,expected",
    [("R$ 5,49", 5.49), ("12,90", 12.90), ("8.99", 8.99), ("129,90", 129.90)],
)
def test_separator_branch_with_short_region(text, expected):
    """Explicitly exercise the [sep] branch with a short region (h<=55).

    A region whose height is below ``min_reais_height`` must still yield the
    correct value when it carries an explicit decimal separator (P1-5).
    """
    regions = [_region(text, cx=100, cy=100, w=120, h=40)]
    prices = reconstruct_prices(regions)
    assert len(prices) == 1
    assert prices[0].source.endswith("[sep]")
    assert prices[0].value == pytest.approx(expected)


def test_reais_without_cents_kept():
    """A lone tall reais number with no nearby cents is still emitted."""
    regions = [_region("50", cx=500, cy=500, w=80, h=90)]
    prices = reconstruct_prices(regions)
    assert prices[0].value == pytest.approx(50.0)


def test_cents_not_stolen_from_far_column():
    """A cents-looking region in a different column must not merge."""
    regions = [
        _region("33", cx=200, cy=600, w=60, h=77),
        _region("90", cx=1800, cy=600, w=40, h=47),  # far away, other column
    ]
    prices = reconstruct_prices(regions)
    # '33' has no valid nearby cents -> 33.0 ; the far '90' is a 2-digit small
    # region, not tall enough to be its own price, so it is ignored.
    assert any(p.value == pytest.approx(33.0) for p in prices)
    assert all(p.value != pytest.approx(33.90) for p in prices)


@pytest.mark.parametrize(
    "text",
    [
        "Cliente APP",
        "Cllente APP pagando",
        "com o Cartão Tenda",
        "Limite por CPF: 30 unidades.",
        "DESCONTO",
        "Preço",
        "Lata 473ml",
        "pagando com o",
    ],
)
def test_boilerplate_detected(text):
    assert is_boilerplate(text) is True
    assert is_product_name(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "Suco de Uva Integral",
        "Queijo Coalho Espeto",
        "Carne Bovina Miolo de Alcatra",
        "Maionese Hellmann's",
    ],
)
def test_real_product_names_pass(text):
    assert is_product_name(text) is True
    assert is_boilerplate(text) is False


@pytest.mark.parametrize("text", ["LEITE", "ARROZ", "CAFE", "TRIGO", "ACUCAR", "FEIJAO"])
def test_short_uppercase_product_names_pass(text):
    """Regression: short all-uppercase words are valid product tokens (P1-1)."""
    assert is_product_name(text) is True


@pytest.mark.parametrize("text", ["AB", "CD", "X", "12", "R$", "..."])
def test_ocr_garble_rejected(text):
    assert is_product_name(text) is False


def test_deduplicate_keeps_promotional_price():
    """Two stacked prices in the same column -> keep the lower (promo)."""
    prices = [
        Price(33.90, _box(1888, 639, 60, 77), "app"),
        Price(31.90, _box(1884, 760, 60, 81), "cartao"),
    ]
    out = deduplicate_dual_prices(prices)
    assert len(out) == 1
    assert out[0].value == pytest.approx(31.90)


def test_deduplicate_keeps_distinct_columns_separate():
    prices = [
        Price(31.90, _box(200, 600, 60, 80), "a"),
        Price(12.90, _box(1400, 600, 60, 80), "b"),
    ]
    out = deduplicate_dual_prices(prices)
    assert len(out) == 2


# --------------------------------------------------------------------------
# Aggregate property tests on the real Tenda fixture
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def flyer_ocr():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


_DENSE_FLYERS = ["flyer_0.jpg", "flyer_1.jpg", "flyer_2.jpg", "flyer_3.jpg"]


@pytest.mark.parametrize("key", _DENSE_FLYERS)
def test_reconstructed_prices_all_in_range(flyer_ocr, key):
    prices = reconstruct_prices(flyer_ocr[key]["regions"])
    assert prices, "expected some prices"
    assert all(0.5 <= p.value <= 250 for p in prices)


@pytest.mark.parametrize("key", _DENSE_FLYERS)
def test_plausible_cents_majority(flyer_ocr, key):
    prices = reconstruct_prices(flyer_ocr[key]["regions"])
    cents = [round((p.value - int(p.value)) * 100) for p in prices]
    plausible = sum(c in _PLAUSIBLE_CENTS for c in cents)
    assert plausible / len(prices) >= 0.80


@pytest.mark.parametrize(
    "key,lo,hi",
    [
        ("flyer_0.jpg", 20, 40),
        ("flyer_1.jpg", 25, 45),
        ("flyer_2.jpg", 25, 45),
        ("flyer_3.jpg", 22, 40),
    ],
)
def test_dedup_yields_realistic_product_count(flyer_ocr, key, lo, hi):
    prices = reconstruct_prices(flyer_ocr[key]["regions"])
    dedup = deduplicate_dual_prices(prices)
    assert lo <= len(dedup) <= hi
    # dedup must not increase the count
    assert len(dedup) <= len(prices)
