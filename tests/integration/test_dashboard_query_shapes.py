"""
Contract tests: validate data shapes from dashboard_queries against real Supabase schema.
Catches column name mismatches (completed_at vs finished_at), missing columns,
and data type mismatches before they reach E2E page crawl.
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

pytestmark = [
    pytest.mark.skipif(
        not (SUPABASE_URL and SUPABASE_SERVICE_KEY and len(SUPABASE_URL) > 10),
        reason="No real Supabase credentials configured",
    ),
    pytest.mark.integration,
]


def get_schema_columns(table: str) -> set[str]:
    """Get column names for a table from Supabase via information_schema."""
    from services.supabase_client import get_service_client

    client = get_service_client()
    r = client.rpc(
        "exec_sql_query",
        {"sql": "SELECT column_name, table_name FROM information_schema.columns WHERE table_schema = 'public'"},
    ).execute()
    cols = set()
    for row in r.data or []:
        if row["table_name"] == table:
            cols.add(row["column_name"])
    return cols


TABLE_COLUMNS: dict[str, set[str]] = {}


def table_columns(table: str) -> set[str]:
    if table not in TABLE_COLUMNS:
        TABLE_COLUMNS[table] = get_schema_columns(table)
    return TABLE_COLUMNS[table]


# ============================================================
# Scraping Logs
# ============================================================


def test_scraping_logs_has_expected_columns():
    """The scraping_logs table must have finished_at (not completed_at)."""
    cols = table_columns("scraping_logs")
    assert "finished_at" in cols, "Scraping_logs missing finished_at — check consolidated_migration.sql:110"
    assert "store_name" in cols
    assert "status" in cols
    assert "started_at" in cols
    assert "items_found" in cols
    assert "items_matched" in cols


def test_get_recent_scraper_logs_shape():
    """Shape returned by get_recent_scraper_logs must match schema."""
    from services.dashboard_queries import get_recent_scraper_logs

    logs = get_recent_scraper_logs(limit=5)
    if not logs:
        pytest.skip("No scraper logs in DB")
    log = logs[0]
    expected = {"store_name", "status", "started_at", "finished_at", "items_found", "items_matched"}
    assert expected.issubset(log.keys()), f"Missing columns in log: {expected - log.keys()}"


def test_get_store_health_shape():
    """get_store_health must return records with store_name, success_rate, etc."""
    from services.dashboard_queries import get_store_health

    health = get_store_health()
    if not health:
        pytest.skip("No health data in DB")
    item = health[0]
    for key in ("store_name", "last_run", "success_rate", "total_runs", "error_count", "avg_items_per_run"):
        assert key in item, f"Missing key '{key}' in health result"


# ============================================================
# Stores
# ============================================================


def test_stores_table_expected_columns():
    """Stores table must have at least id, name, scraper, is_active."""
    cols = table_columns("stores")
    for col in ("id", "name", "scraper", "is_active", "tier"):
        assert col in cols, f"Stores table missing column '{col}'"


def test_get_stores_with_frequencies_shape():
    """get_stores_with_frequencies must return stores with expected fields."""
    from services.dashboard_queries import get_stores_with_frequencies

    stores = get_stores_with_frequencies()
    assert len(stores) > 0, "No stores returned"
    s = stores[0]
    for key in ("id", "name", "is_active"):
        assert key in s, f"Missing key '{key}' in store"


# ============================================================
# Prices
# ============================================================


def test_prices_table_expected_columns():
    """Prices table must have ingredient_id, store_id, raw_price, price_per_kg."""
    cols = table_columns("prices")
    for col in ("ingredient_id", "store_id", "raw_price", "price_per_kg", "collected_at", "normalized"):
        assert col in cols, f"Prices table missing column '{col}'"


def test_get_latest_prices_cached_shape():
    """get_latest_prices_cached must return prices with expected columns."""
    from services.dashboard_queries import get_latest_prices_cached

    prices = get_latest_prices_cached(limit=10)
    if not prices:
        pytest.skip("No prices in DB")
    p = prices[0]
    for key in ("ingredient_id", "store_id", "raw_price", "price_per_kg", "collected_at", "normalized"):
        assert key in p, f"Missing key '{key}' in price row"


# ============================================================
# Cross-ingredient ranking
# ============================================================


def test_get_cross_ingredient_ranking_shape():
    """get_cross_ingredient_ranking returns rows with store_name, top1_count, top3_count, total_ingredients."""
    from services.dashboard_queries import get_cross_ingredient_ranking_cached

    ranking = get_cross_ingredient_ranking_cached(days=90)
    if not ranking:
        pytest.skip("No ranking data in DB")
    r = ranking[0]
    for key in ("store_name", "top1_count", "top3_count"):
        assert key in r, f"Missing key '{key}' in ranking row"


# ============================================================
# Config tables
# ============================================================


def test_ingredients_table_columns():
    """Ingredients table must have canonical_name, active."""
    cols = table_columns("ingredients")
    for col in ("id", "canonical_name", "active", "category"):
        assert col in cols, f"Ingredients table missing column '{col}'"


def test_flyers_table_columns():
    """Flyers table must have expected columns."""
    cols = table_columns("flyers")
    if cols:
        for col in ("id", "store_name", "flyer_date_start", "flyer_date_end"):
            assert col in cols, f"Flyers table missing column '{col}'"
