"""Unit tests for main.py --tier dispatch and --finalize gating.

Root-cause coverage: main.py previously parsed --tier but never dispatched on
it, so the scrape workflow matrix [1, 2a, 2b, 3] launched 4
*identical* full-collection runs (4x I/O, 4x emails, 4x cleanups).
These tests prove each tier collects only its own collectors and that
finalize runs exactly once (pulling all prices from DB).
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import main as main_mod  # noqa: E402
import services  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Congela time.sleep — o fluxo main→price_repository tem retries com
    backoff real (~3-6s por teste de dispatch)."""
    monkeypatch.setattr("time.sleep", lambda *_: None)


@pytest.fixture
def harness(tmp_path):
    """Patch every collector + side-effect so main() can run offline."""
    ingredient = {"id": "ing1", "name": "Leite"}

    # Build a mock per collector method named in TIER_PLAN.
    mocks: dict[str, MagicMock] = {}
    for _tier, method, _needs in main_mod.TIER_PLAN:
        m = MagicMock(return_value=[])
        mocks[method] = m
    mocks["process_ocr_queue"] = MagicMock(return_value=3)

    # Finalize-only DB pull.
    db_prices = [{"ingredient_id": "ing1", "raw_price": 10.0}]

    collector_attrs = {
        "load_ingredients": MagicMock(return_value=[ingredient]),
        **{m: mocks[m] for m in mocks},
    }
    price_repo = MagicMock()
    price_repo.get_latest_prices = MagicMock(return_value=db_prices)

    pi = MagicMock()
    pi.enrich_prices.side_effect = lambda prices: prices

    alert = MagicMock()
    alert.process_proactive_alerts = MagicMock()

    with patch.multiple(
        main_mod.collector,
        **collector_attrs,
    ), patch.object(
        main_mod, "sync_store_fields", MagicMock(return_value=1)
    ), patch.object(
        main_mod, "sync_scrape_frequencies", MagicMock(return_value=1)
    ), patch.object(
        # Batem no Supabase real (TLS ~3-4s cada) se não mockados.
        main_mod, "sync_store_units", MagicMock(return_value=1)
    ), patch.object(
        main_mod, "cleanup_test_data", MagicMock(return_value={})
    ), patch.object(
        main_mod.store_registry,
        "discover_stores_from_flyers",
        MagicMock(),
    ), patch.object(
        # Lazy import dentro de _finalize() — sem mock bate no Supabase real (HTTP/2, ~3s).
        main_mod.store_registry,
        "auto_promote_discovered_stores",
        MagicMock(return_value=0),
    ), patch.object(
        main_mod.price_intelligence, "PriceIntelligence", return_value=pi
    ), patch.object(
        main_mod.price_analytics,
        "generate_report_html",
        MagicMock(return_value="<html/>"),
    ), patch.object(
        main_mod.email_service, "send_daily_report", MagicMock()
    ), patch.object(
        main_mod.price_service,
        "cleanup_old_prices",
        MagicMock(return_value="ok"),
    ), patch.object(
        main_mod.price_service,
        "cleanup_old_logs",
        MagicMock(return_value="ok"),
    ), patch.object(
        main_mod.price_service,
        "cleanup_old_flyers_all",
        MagicMock(return_value="ok"),
    ), patch.object(
        main_mod.price_service,
        "cleanup_resolved_review_items",
        MagicMock(return_value=0),
    ), patch.object(
        main_mod.price_service,
        "auto_reject_stale_review_items",
        MagicMock(return_value=0),
    ), patch.object(
        main_mod.flyer_service,
        "cleanup_old_flyers",
        MagicMock(return_value="ok"),
    ), patch.object(
        main_mod.flyer_service,
        "cleanup_non_food_flyers",
        MagicMock(return_value="ok"),
    ), patch.dict(
        sys.modules,
        {"services.alert_service": alert, "services.price_repository": price_repo},
    ), patch.object(
        # Override the attribute bound on the services module object (set when
        # another test imports services.alert_service for real), so that
        # main.py's lazy `from services import alert_service` resolves to the mock.
        services, "alert_service", alert, create=True,
    ), patch.object(
        main_mod, "DATA_DIR", tmp_path
    ):
        yield SimpleNamespace(mocks=mocks, pi=pi, price_repo=price_repo, alert=alert)


def _args(argv):
    """Build a main() args namespace from a CLI-style list."""
    kwargs = {
        "tier": None,
        "finalize": False,
        "no_finalize": False,
        "dry_run": False,
        "force": False,
        "mode": "cron",
        "stores_filter": None,
    }
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--tier":
            kwargs["tier"] = argv[i + 1]
            i += 2
            continue
        if a == "--stores-filter":
            kwargs["stores_filter"] = argv[i + 1]
            i += 2
            continue
        if a == "--finalize":
            kwargs["finalize"] = True
        if a == "--no-finalize":
            kwargs["no_finalize"] = True
        if a == "--dry-run":
            kwargs["dry_run"] = True
        if a == "--force":
            kwargs["force"] = True
        i += 1
    return SimpleNamespace(**kwargs)


def test_tier_1_collects_only_tier1(harness):
    main_mod.main(_args(["--tier", "1"]))
    # Tier-1 collectors must run.
    assert harness.mocks["collect_tier1_pdfs"].called
    assert harness.mocks["collect_extra_flyers"].called
    assert harness.mocks["collect_pao_flyers"].called
    assert harness.mocks["collect_roldao_flyer"].called
    assert harness.mocks["process_ocr_queue"].called
    # Tier-2a / 2b / 3 collectors must NOT run.
    assert not harness.mocks["collect_tier2_vtex"].called
    assert not harness.mocks["collect_carrefour"].called
    assert not harness.mocks["collect_tier2_js"].called
    assert not harness.mocks["collect_tier3_websites"].called
    assert not harness.mocks["collect_aggregators_ssr"].called
    assert not harness.mocks["collect_aggregators_js"].called
    assert not harness.mocks["collect_facebook_flyers"].called
    # --tier implies --no-finalize: no enrich / email / cleanup.
    assert not harness.pi.enrich_prices.called
    assert not harness.alert.process_proactive_alerts.called


def test_tier_3_collects_only_tier3(harness):
    main_mod.main(_args(["--tier", "3"]))
    assert harness.mocks["collect_tier3_websites"].called
    assert harness.mocks["collect_aggregators_ssr"].called
    assert harness.mocks["collect_aggregators_js"].called
    assert harness.mocks["collect_facebook_flyers"].called
    # Tier-1 / 2a collectors must NOT run.
    assert not harness.mocks["collect_tier1_pdfs"].called
    assert not harness.mocks["collect_tier2_vtex"].called
    assert not harness.mocks["collect_carrefour"].called


def test_finalize_only_pulls_db_and_finalizes_once(harness):
    main_mod.main(_args(["--finalize"]))
    # No collectors run in finalize-only mode.
    for m in harness.mocks.values():
        assert not m.called, f"collector {m} ran in finalize-only mode"
    # Finalize pulls all prices from DB, enriches, emails, alerts.
    assert harness.price_repo.get_latest_prices.called
    assert harness.pi.enrich_prices.called
    assert harness.alert.process_proactive_alerts.called


def test_full_local_run_collects_all_and_finalizes(harness):
    main_mod.main(_args([]))
    # All collectors run in a full local run.
    for method, m in harness.mocks.items():
        if method == "process_ocr_queue":
            continue
        assert m.called, f"collector {method} not called in full run"
    # Finalize runs.
    assert harness.pi.enrich_prices.called
    assert harness.alert.process_proactive_alerts.called


def test_no_finalize_skips_side_effects(harness):
    main_mod.main(_args(["--tier", "2a", "--no-finalize"]))
    assert harness.mocks["collect_tier2_vtex"].called
    assert not harness.mocks["collect_tier1_pdfs"].called
    assert not harness.pi.enrich_prices.called
    assert not harness.alert.process_proactive_alerts.called


def test_stores_filter_sets_env_var(harness):
    with patch.dict("os.environ", {}, clear=True):
        main_mod.main(_args(["--tier", "2a", "--stores-filter", "Tiendeo, Carrefour Mercado"]))
        assert os.environ.get("CUSTODOCE_STORES_FILTER") == "Tiendeo, Carrefour Mercado"


def test_stores_filter_absent_leaves_env_clean(harness):
    with patch.dict("os.environ", {}, clear=True):
        main_mod.main(_args(["--tier", "2a"]))
    assert "CUSTODOCE_STORES_FILTER" not in os.environ
