"""Unit tests for services/dashboard_queries.py (KPIs e lookups cached)."""

from __future__ import annotations

from unittest.mock import patch

from services import dashboard_queries
from tests.unit.fixtures.mock_data import MOCK_INGREDIENTS, MOCK_PRICES, MOCK_STORES


def _prices():
    return [
        {"ingredient_id": p["ingredient_id"], "store_id": p["store_id"], "normalized": {"price_per_kg": p["price_per_kg"]}}
        for p in MOCK_PRICES
    ]


def test_get_dashboard_kpis_empty():
    with patch.object(dashboard_queries, "get_all_current_prices", return_value=[]):
        kpis = dashboard_queries.get_dashboard_kpis()
    assert kpis["total_prices"] == 0
    assert kpis["avg_price_per_kg"] == 0


def test_get_dashboard_kpis_computes():
    with patch.object(dashboard_queries, "get_all_current_prices", return_value=_prices()):
        kpis = dashboard_queries.get_dashboard_kpis()
    assert kpis["total_prices"] == len(_prices())
    assert kpis["ingredients_covered"] == len({p["ingredient_id"] for p in _prices()})
    assert kpis["stores_active"] == len({p["store_id"] for p in _prices()})
    assert kpis["avg_price_per_kg"] > 0


def test_get_ingredient_by_canonical_found():
    with patch.object(dashboard_queries, "cached_get_all_ingredients", return_value=MOCK_INGREDIENTS):
        ing = dashboard_queries.get_ingredient_by_canonical("Leite Condensado")
    assert ing is not None
    assert ing["id"] == "ing-001"


def test_get_ingredient_by_canonical_missing():
    with patch.object(dashboard_queries, "cached_get_all_ingredients", return_value=MOCK_INGREDIENTS):
        ing = dashboard_queries.get_ingredient_by_canonical("Inexistente")
    assert ing is None


def test_get_store_scraper_config():
    with patch.object(dashboard_queries, "cached_get_all_stores", return_value=MOCK_STORES):
        cfg = dashboard_queries.get_store_scraper_config("Assaí Atacadista")
    assert cfg is not None
    assert cfg["scraper"] == "base_flyer"


def test_get_active_stores_by_tier():
    with patch.object(dashboard_queries, "cached_get_all_stores", return_value=MOCK_STORES):
        tier1 = dashboard_queries.get_active_stores_by_tier(tier=1)
    assert all(s["tier"] == 1 for s in tier1)
    assert len(tier1) >= 1
