"""Consumer tests: MOCK_INGREDIENTS + MOCK_PRICES drive matcher logic."""

from __future__ import annotations

from parsers import matcher
from tests.unit.fixtures.mock_data import MOCK_INGREDIENTS, MOCK_PRICES


def test_mock_ingredients_build_alias_list_covers_search_terms():
    aliases = matcher.build_alias_list(MOCK_INGREDIENTS)
    assert len(aliases) == sum(
        1 + len(ing.get("aliases", [])) + len(ing.get("search_terms", []))
        for ing in MOCK_INGREDIENTS
    )
    flat = [a[1] for a in aliases]
    assert "leite condensado" in flat  # search_term do ing-001
    assert "creme de leite" in flat  # search_term do ing-002


def test_mock_prices_match_expected_ingredient():
    expected = {
        "price-001": "Leite Condensado",
        "price-002": "Leite Condensado",
        "price-003": "Creme de Leite",
    }
    for price in MOCK_PRICES:
        ing, score, match_type = matcher.match_ingredient(price["raw_product"], MOCK_INGREDIENTS)
        assert ing is not None, f"sem match para {price['raw_product']}"
        assert ing["canonical_name"] == expected[price["id"]]
        assert score >= 80.0


def test_mock_prices_search_term_boosts_match():
    # "Leite Moça 395g" contém search_term "leite moça" do ing-001
    ing, score, match_type = matcher.match_ingredient(
        "Leite Moça 395g", MOCK_INGREDIENTS
    )
    assert ing is not None
    assert ing["canonical_name"] == "Leite Condensado"
    assert score >= 80.0
