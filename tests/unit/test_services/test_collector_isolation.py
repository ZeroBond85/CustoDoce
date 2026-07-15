"""Regression tests for process-isolated scraper execution.

The previous implementation wrapped only ``scraper.run()`` in a thread-based
timeout. A hang during browser *launch* (``cls(store)`` / ``__enter__``) had no
timeout at all, and ``future.cancel()`` does not kill the underlying Chrome
process — leaving a zombie that wedged every subsequent store and pinned the
whole CI job at the 130min job timeout.

``_run_scraper_isolated`` runs each scraper in a separate OS process with a
hard timeout that terminates the process (and its browser children) on expiry.
These tests prove a hung scraper can no longer wedge the caller.
"""

from __future__ import annotations

import time

from services.collector import _run_scraper_isolated


class _GoodScraper:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, ingredients=None):
        self._thumbnail = b"thumb"
        return [{"product": "Leite Condensado 395g", "price": 4.5, "unit": "un"}]


class _HangRunScraper:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, ingredients=None):
        time.sleep(3600)  # hang forever inside run()
        return []


class _HangLaunchScraper:
    def __init__(self, store):
        time.sleep(3600)  # hang during browser launch

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, ingredients=None):
        return []


def test_isolated_happy_path_returns_products_and_thumbnail():
    raw, thumb = _run_scraper_isolated(_GoodScraper, {"name": "X"}, [], True, "X", timeout_seconds=10)
    assert len(raw) == 1
    assert raw[0]["product"] == "Leite Condensado 395g"
    assert thumb == b"thumb"


def test_isolated_timeout_on_run_does_not_wedge():
    t0 = time.time()
    raw, thumb = _run_scraper_isolated(_HangRunScraper, {"name": "X"}, [], True, "X", timeout_seconds=2)
    elapsed = time.time() - t0
    assert raw == []
    assert thumb is None
    # Must return well within any job budget — prove there is no 2h wedge.
    assert elapsed < 20


def test_isolated_timeout_on_launch_does_not_wedge():
    t0 = time.time()
    raw, thumb = _run_scraper_isolated(_HangLaunchScraper, {"name": "X"}, [], True, "X", timeout_seconds=2)
    elapsed = time.time() - t0
    assert raw == []
    assert thumb is None
    assert elapsed < 20
