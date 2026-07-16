"""Regression tests for collector.LAST_RUN_STATS.

``_scrape_store`` records the raw extracted count and matched count into
``collector.LAST_RUN_STATS[store_name]``. Diagnostic tooling
(``scripts/test_single_store.py``) uses this to distinguish:

- ``extracted == 0``  -> real failure (timeout / rate-limit / dead site / OCR hang)
- ``extracted > 0`` but ``matched == 0`` -> viable store whose flyer simply has no
  monitored confectionery ingredients this week (e.g. a general supermarket flyer).

Without this, both cases collapse to ``collected == 0`` and a working store gets
flagged as broken.
"""

from __future__ import annotations

import services.collector as collector
from services.collector import _scrape_store


class _SafeHttpScraper:
    """Runs in the parent process (safe_in_parent) and returns raw products."""

    safe_in_parent = True

    def __init__(self, store):
        self.store = store
        self._products = store.get("_fake_products", [])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, ingredients=None):
        return list(self._products)


def _match_all(store, prod, ingredients):
    return {"store_name": store["name"], "product": prod["product"], "price": prod["price"]}


def _match_none(store, prod, ingredients):
    return None


def test_stats_record_extracted_and_matched(monkeypatch):
    monkeypatch.setattr(collector, "LAST_RUN_STATS", {})
    monkeypatch.setattr(collector, "log_scraper_run", lambda *a, **k: None)
    monkeypatch.setattr(collector, "_check_zero_products_alert", lambda *a, **k: None)

    store = {
        "name": "FakeStore",
        "_fake_products": [
            {"product": "Leite Condensado 395g", "price": 4.5, "unit": "un"},
            {"product": "Creme de Leite 200g", "price": 2.9, "unit": "un"},
        ],
    }
    name, entries = _scrape_store(store, _SafeHttpScraper, [], "test", True, _match_all, 30)

    assert name == "FakeStore"
    assert len(entries) == 2
    assert collector.LAST_RUN_STATS["FakeStore"] == {"extracted": 2, "matched": 2}


def test_stats_extracted_but_zero_matched_is_not_a_failure(monkeypatch):
    """Flyer de supermercado geral: extraiu produtos, mas 0 são ingredientes monitorados."""
    monkeypatch.setattr(collector, "LAST_RUN_STATS", {})
    monkeypatch.setattr(collector, "log_scraper_run", lambda *a, **k: None)
    monkeypatch.setattr(collector, "_check_zero_products_alert", lambda *a, **k: None)

    store = {
        "name": "GeneralFlyerStore",
        "_fake_products": [
            {"product": "Batata Kg", "price": 3.5, "unit": "kg"},
            {"product": "Ovo Branco Dz", "price": 9.9, "unit": "dz"},
        ],
    }
    name, entries = _scrape_store(store, _SafeHttpScraper, [], "test", True, _match_none, 30)

    assert entries == []
    stats = collector.LAST_RUN_STATS["GeneralFlyerStore"]
    assert stats["extracted"] == 2
    assert stats["matched"] == 0


def test_stats_zero_extracted_is_a_failure(monkeypatch):
    monkeypatch.setattr(collector, "LAST_RUN_STATS", {})
    monkeypatch.setattr(collector, "log_scraper_run", lambda *a, **k: None)
    monkeypatch.setattr(collector, "_check_zero_products_alert", lambda *a, **k: None)

    store = {"name": "DeadStore", "_fake_products": []}
    name, entries = _scrape_store(store, _SafeHttpScraper, [], "test", True, _match_all, 30)

    assert entries == []
    assert collector.LAST_RUN_STATS["DeadStore"] == {"extracted": 0, "matched": 0}


def test_suppress_local_scope_bug_in_parent_process(monkeypatch):
    """Regressão (Python 3.14 strict scoping): `with suppress` no except/finally

    de `_collect_prices` falhava com 'cannot access local variable suppress'
    quando o scraper usava o processo pai (`safe_in_parent` ativo) e o import
    local `from contextlib import suppress` poluía o escopo da função. O erro
    só ocorria no branch do `except` (transient/error), não no happy path.
    """
    from contextlib import suppress as real_suppress

    monkeypatch.setattr(collector, "LAST_RUN_STATS", {})
    monkeypatch.setattr(collector, "log_scraper_run", lambda *a, **k: None)
    monkeypatch.setattr(collector, "_check_zero_products_alert", lambda *a, **k: None)
    monkeypatch.setattr(
        collector, "_run_scraper_isolated",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("transient net")),
    )

    class _IsolatedScraper:
        safe_in_parent = False

        def __init__(self, store):
            self.store = store

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def run(self, ingredients=None):
            return []

    store = {"name": "NetFlaky", "_fake_products": [{"product": "Leite 1L", "price": 4.0}]}
    # Should not raise 'cannot access local variable suppress'
    with real_suppress(Exception):
        name, entries = _scrape_store(store, _IsolatedScraper, [], "test", False, _match_none, 30)

    assert name == "NetFlaky"
    assert entries == []
