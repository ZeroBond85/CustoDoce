"""Regression: config jsonb column must be promoted to top-level for scrapers.

Root cause (Rede Krill): browse_urls/api_base/anti_bot/etc are NOT columns of
the stores table; they live in the `config` jsonb. Without merging them up,
scrapers run without their config (e.g. Krill falls into the broken /busca?q=
search mode and returns 0 products after burning the full timeout).
"""

from services.collector import _merge_store_config


def test_merge_promotes_config_keys_to_top_level():
    store = {
        "id": "rede_krill",
        "name": "Rede Krill",
        "scraper": "playwright_price_scraper",
        "config": {
            "browse_urls": ["https://x/dep-1", "https://x/dep-2"],
            "anti_bot": True,
        },
    }
    merged = _merge_store_config(store)
    assert merged["browse_urls"] == ["https://x/dep-1", "https://x/dep-2"]
    assert merged["anti_bot"] is True
    assert merged["name"] == "Rede Krill"


def test_merge_db_columns_win_over_config():
    store = {
        "name": "Store",
        "base_url": "https://real.example",
        "config": {"base_url": "https://stale.example", "extra": 1},
    }
    merged = _merge_store_config(store)
    assert merged["base_url"] == "https://real.example"
    assert merged["extra"] == 1


def test_merge_handles_missing_or_nondict_config():
    assert _merge_store_config({"name": "A"})["name"] == "A"
    assert _merge_store_config({"name": "B", "config": None})["name"] == "B"
    assert _merge_store_config({"name": "C", "config": {}})["name"] == "C"
    assert _merge_store_config({"name": "D", "config": True})["name"] == "D"
