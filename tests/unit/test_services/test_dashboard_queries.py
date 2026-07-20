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


def test_get_store_coverage_health_flags_stale_and_fresh():
    """Loja com preço recente = fresca; loja sem preço = stale (visão no dia a dia)."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    recent = (now - timedelta(days=1)).isoformat()
    old = (now - timedelta(days=10)).isoformat()

    stores = [
        {"id": "s1", "name": "Fresca", "tier": 1},
        {"id": "s2", "name": "Velha", "tier": 1},
        {"id": "s3", "name": "Nunca", "tier": 2},
    ]
    prices = [
        {"store_id": "s1", "ingredient_id": "Leite", "valid_from": recent, "collected_at": recent},
        {"store_id": "s2", "ingredient_id": "Leite", "valid_from": old, "collected_at": old},
    ]
    with patch.object(dashboard_queries, "cached_get_all_stores", return_value=stores), patch.object(
        dashboard_queries, "get_latest_prices_cached", return_value=prices
    ):
        cov = dashboard_queries.get_store_coverage_health(stale_days=3)
    by_name = {c["store_name"]: c for c in cov}
    assert by_name["Fresca"]["is_stale"] is False
    assert by_name["Fresca"]["days_since_price"] == 1
    assert by_name["Velha"]["is_stale"] is True
    assert by_name["Nunca"]["is_stale"] is True
    assert by_name["Nunca"]["days_since_price"] is None


def test_get_store_coverage_health_handles_naive_timestamps():
    """Regressão: collected_at sem timezone (naive) não pode quebrar o subtract.

    Timestamps do DB podem vir sem offset ("2026-07-20 18:00:00"). Antes, o parse
    produzia datetime naive e ``(datetime.now(UTC) - last_dt)`` lançava
    ``TypeError: can't subtract offset-naive and offset-aware datetimes``,
    derrubando a página Scraper Health.
    """
    from datetime import datetime, timedelta

    naive_now = datetime.now()  # noqa: DTZ005 - intencional: simula timestamp naive do DB
    recent_naive = (naive_now - timedelta(days=2)).isoformat()  # sem offset

    stores = [{"id": "s1", "name": "Naive", "tier": 1}]
    prices = [{"store_id": "s1", "ingredient_id": "Leite", "collected_at": recent_naive}]
    with patch.object(dashboard_queries, "cached_get_all_stores", return_value=stores), patch.object(
        dashboard_queries, "get_latest_prices_cached", return_value=prices
    ):
        cov = dashboard_queries.get_store_coverage_health(stale_days=3)
    naive = next(c for c in cov if c["store_name"] == "Naive")
    assert naive["days_since_price"] in (1, 2)  # tolera fuso; não deve lançar
    assert naive["is_stale"] is False


def test_get_coverage_summary_pct():
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    recent = (now - timedelta(days=1)).isoformat()
    stores = [
        {"id": "s1", "name": "Fresca", "tier": 1},
        {"id": "s2", "name": "Nunca", "tier": 2},
    ]
    prices = [{"store_id": "s1", "ingredient_id": "Leite", "valid_from": recent, "collected_at": recent}]
    with patch.object(dashboard_queries, "cached_get_all_stores", return_value=stores), patch.object(
        dashboard_queries, "get_latest_prices_cached", return_value=prices
    ):
        summary = dashboard_queries.get_coverage_summary(stale_days=3)
    assert summary["total_stores"] == 2
    assert summary["fresh"] == 1
    assert summary["stale"] == 1
    assert summary["coverage_pct"] == 50.0
