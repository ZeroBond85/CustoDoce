from unittest.mock import MagicMock, patch

from services.dashboard_queries import (
    get_active_promotions,
    get_coverage_by_ingredient,
    get_dashboard_kpis,
    get_scraper_health_dashboard,
)
from tests.unit.fixtures.mock_data import MOCK_LATEST_PRICES, MOCK_SCRAPING_LOGS


@patch("services.dashboard_queries.get_latest_prices_cached")
def test_get_dashboard_kpis_contract(mock_get_prices):
    mock_get_prices.return_value = MOCK_LATEST_PRICES
    kpis = get_dashboard_kpis()
    expected_keys = {"total_prices", "ingredients_covered", "stores_active", "avg_price_per_kg"}
    assert set(kpis.keys()) == expected_keys
    assert isinstance(kpis["total_prices"], int)
    assert isinstance(kpis["avg_price_per_kg"], (int, float))


@patch("services.dashboard_queries.get_latest_prices_cached")
def test_get_coverage_by_ingredient_contract(mock_get_prices):
    mock_get_prices.return_value = MOCK_LATEST_PRICES
    coverage = get_coverage_by_ingredient()
    assert isinstance(coverage, list)
    if coverage:
        item = coverage[0]
        expected_keys = {"ingredient", "stores", "prices", "min_ppk", "avg_ppk", "store_count"}
        assert expected_keys.issubset(set(item.keys()))
        assert isinstance(item["stores"], list)
        assert isinstance(item["store_count"], int)


@patch("services.dashboard_queries.get_latest_prices_cached")
def test_get_active_promotions_contract(mock_get_prices):
    mock_get_prices.return_value = MOCK_LATEST_PRICES
    promos = get_active_promotions()
    assert isinstance(promos, list)
    if promos:
        assert "is_promotion" in promos[0]
        assert promos[0]["is_promotion"] is True


@patch("services.dashboard_queries.get_supabase")
def test_get_scraper_health_dashboard_contract(mock_get_supabase):
    mock_client = MagicMock()
    mock_get_supabase.return_value = mock_client
    mock_execute = MagicMock()
    mock_execute.data = MOCK_SCRAPING_LOGS
    mock_client.table().select().order().limit().execute.return_value = mock_execute

    health = get_scraper_health_dashboard()
    assert isinstance(health, list)
    if health:
        item = health[0]
        expected_keys = {
            "store_name",
            "last_run",
            "success_rate",
            "latency_p95_ms",
            "avg_items_per_run",
            "total_runs",
            "error_count",
            "total_items",
            "status_label",
            "status_color",
            "latency_label",
        }
        assert expected_keys.issubset(set(item.keys()))
        emoji_ok = "🟢" in item["status_label"] or "🟡" in item["status_label"] or "🔴" in item["status_label"]
        assert emoji_ok, f"expected status emoji in label, got {item['status_label']}"
