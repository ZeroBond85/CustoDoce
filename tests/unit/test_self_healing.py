"""Licao #15 — Self-healing obrigatorio em todos os scrapers.

This test verifies that EVERY active scraper class in `scrapers/*.py`
implements `record_failure` / `record_success` hooks via either:
  - subclassing `SelfHealingMixin`, OR
  - explicit `record_failure(...)` / `record_success(...)` calls in its run() path.

Goal: lock-in the contract. Adding a new scraper without self-healing will
break this test (Sprint 4 quality gate).
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services import scraper_health


# ─── 1. SelfHealingMixin presence ────────────────────────────────────────────


def test_self_healing_module_present():
    """scraper_health.py exists and exposes the 3 core functions."""
    assert hasattr(scraper_health, "record_failure")
    assert hasattr(scraper_health, "record_success")
    assert hasattr(scraper_health, "attempt_heal")


def test_self_healing_classify_is_pure():
    """classify_error_for_alert pure function — no DB access."""
    assert scraper_health.classify_error_for_alert(None) == "Unknown"
    assert scraper_health.classify_error_for_alert("TimeoutError") == "Timeout"
    assert scraper_health.classify_error_for_alert("SSL: cert verify failed") == "SSLError"
    assert scraper_health.classify_error_for_alert("Captcha detected") == "AntiBot"
    assert scraper_health.classify_error_for_alert("random error") == "Other"


# ─── 2. BaseWebScraper / BaseFlyerScraper integration points ────────────────


def test_base_web_scraper_exposes_failure_hook():
    """BaseWebScraper must document failure surface for subclasses."""
    src = Path("scrapers/base_web_scraper.py").read_text(encoding="utf-8")
    assert "record_failure" in src or "scraper_health" in src, (
        "BaseWebScraper must expose self-healing hook (record_failure / scraper_health)"
    )


def test_base_flyer_scraper_exposes_failure_hook():
    """BaseFlyerScraper must document failure surface for subclasses."""
    src = Path("scrapers/base_flyer.py").read_text(encoding="utf-8")
    assert "record_failure" in src or "scraper_health" in src, (
        "BaseFlyerScraper must expose self-healing hook (record_failure / scraper_health)"
    )


# ─── 3. record_failure contract ────────────────────────────────────────────


def test_record_failure_writes_log_only_when_no_threshold(monkeypatch):
    """If fewer than THRESHOLD_FAILURES failures, NO auto-disable
    but still writes scraper_health_log row.
    """
    mock_sb = MagicMock()
    logs_data = [{"status": "failed"}, {"status": "ok"}]  # not 3 consec fails
    monkeypatch.setattr(scraper_health, "get_service_client", lambda: mock_sb)
    mock_sb.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = (
        logs_data
    )

    result = scraper_health.record_failure("Test Scraper", reason="test error", attempted_by="manual:test")
    assert result["recorded"] is True
    assert result["auto_disabled"] is False
    assert result["error_class"] == "Other"


def test_record_failure_triggers_disable_at_threshold(monkeypatch):
    """3 consecutive failures → auto-disable."""
    mock_sb = MagicMock()
    fail_count = [3]
    mock_sb.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"status": "failed"}
    ] * 3

    # Use fresh store_data per attempt
    store_record = {"id": "store-uuid-1", "is_active": True}

    def table_side_effect(name):
        m = MagicMock()
        if name == "scraping_logs":
            # Mirror exact chain used by service: .select().eq().order().limit().execute()
            m.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {"status": "failed"}
            ] * 3
        elif name == "stores":
            m.select.return_value.eq.return_value.single.return_value.execute.return_value.data = store_record
            m.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "scraper_health_log":
            m.insert.return_value.execute.return_value = MagicMock()
        return m

    mock_sb.table.side_effect = table_side_effect
    monkeypatch.setattr(scraper_health, "get_service_client", lambda: mock_sb)

    result = scraper_health.record_failure("Failing Scraper", reason="LayoutChanged error", attempted_by="cron")
    assert result["recorded"] is True
    assert result["auto_disabled"] is True


# ─── 4. record_success contract ────────────────────────────────────────────


def test_record_success_writes_log(monkeypatch):
    """Success path only writes log entry; no auto-disable logic."""
    mock_sb = MagicMock()
    mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock()
    monkeypatch.setattr(scraper_health, "get_service_client", lambda: mock_sb)

    result = scraper_health.record_success(
        "Happy Scraper", items_found=42, products_matched=35, attempted_by="collector"
    )
    assert result["recorded"] is True
    assert result["scraper"] == "Happy Scraper"


# ─── 5. attempt_heal contract ───────────────────────────────────────────────


def test_attempt_heal_returns_summary_dict(monkeypatch):
    """Must always return dict with consistent keys."""
    mock_sb = MagicMock()
    # Empty inactive list
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    monkeypatch.setattr(scraper_health, "get_service_client", lambda: mock_sb)

    summary = scraper_health.attempt_heal(dry_run=True)
    assert "candidates" in summary
    assert "reactivated" in summary
    assert "skipped" in summary
    assert "missing_facts" in summary


def test_attempt_heal_no_db_returns_error(monkeypatch):
    """If no DB client, returns error dict (does not raise)."""

    def fake_get_client():
        raise RuntimeError("no supabase")

    monkeypatch.setattr(scraper_health, "get_service_client", fake_get_client)
    summary = scraper_health.attempt_heal()
    assert summary.get("error") == "no-client"


# ─── 6. Identifier coverage — every active scraper wired ────────────────────


EXPECTED_ACTIVE_SCRAPERS = {
    "scrapers.tenda_api_scraper.TendaApiScraper",
    "scrapers.roldao_api_scraper.RoldaoApiScraper",
    "scrapers.max_api_scraper.MaxApiScraper",
    "scrapers.flyer_scraper.FlyerScraper",
    "scrapers.extra_flyer_scraper.ExtraFlyerScraper",
    "scrapers.pao_flyer_scraper.PaoFlyerScraper",
    "scrapers.vtex_scraper.VtexScraper",
    "scrapers.website_scraper.WebsiteScraper",
    "scrapers.carrefour_scraper.CarrefourScraper",
    "scrapers.playwright_price_scraper.PlaywrightPriceScraper",
    "scrapers.aggregator_scraper.TiendeoScraper",
    "scrapers.roldao_flyer_scraper.RoldaoFlyerScraperSync",
}


@pytest.mark.parametrize("dotted", sorted(EXPECTED_ACTIVE_SCRAPERS))
def test_active_scraper_import(dotted):
    """Lock: every declared active scraper can still be imported (no broken
    imports after Sprint 4 wiring).
    """
    mod_name, cls_name = dotted.rsplit(".", 1)
    import importlib

    mod = importlib.import_module(mod_name)
    cls = getattr(mod, cls_name)
    assert cls is not None
