"""
CustoDoce - Main Orchestrator
Coordinates collection, cleaning, intelligence, and reporting.
"""

import json
import os
import threading
import time
from argparse import ArgumentParser, Namespace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from services.types import Ingredient, PriceEntry
from collections.abc import Callable

from scripts.sync_all_store_fields import sync_scrape_frequencies, sync_store_fields, sync_store_units
from services import collector, email_service, flyer_service, otel, price_analytics, price_intelligence, price_service, store_registry
from services.maintenance_service import cleanup_test_data
from services.logger import logger

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


class CircuitBreaker:
    """Simple circuit breaker to prevent cascading failures.

    States: CLOSED (normal), OPEN (failing), HALF_OPEN (testing recovery).
    Opens after `failure_threshold` consecutive failures.
    Auto-closes after `recovery_timeout` seconds when in HALF_OPEN with success.
    """

    def __init__(self, name: str, failure_threshold: int = 3, recovery_timeout: int = 300) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "OPEN" and self._last_failure_time is not None and time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = "HALF_OPEN"
                logger.info("circuit_breaker_half_open", name=self.name)
            return self._state

    def is_available(self) -> bool:
        return self.state != "OPEN"

    def record_success(self) -> None:
        with self._lock:
            if self._state == "HALF_OPEN":
                self._state = "CLOSED"
                self._failure_count = 0
                logger.info("circuit_breaker_closed", name=self.name)
            elif self._state == "CLOSED":
                self._failure_count = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.failure_threshold:
                self._state = "OPEN"
                logger.warning("circuit_breaker_opened", name=self.name, failures=self._failure_count)


# Circuit breakers per tier/method
_CIRCUIT_BREAKERS: dict[str, CircuitBreaker] = {}


def _get_circuit_breaker(name: str) -> CircuitBreaker:
    if name not in _CIRCUIT_BREAKERS:
        _CIRCUIT_BREAKERS[name] = CircuitBreaker(name)
    return _CIRCUIT_BREAKERS[name]


DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


def parse_args() -> Namespace:
    parser = ArgumentParser(description="CustoDoce Main Orchestrator")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run mode: skip external side-effects (alerts, email, cleanups)")
    parser.add_argument("--tier", type=str, default=None, help="Scraping tier to collect (1/2a/2b/3). None = all tiers.")
    parser.add_argument("--mode", type=str, default="cron", help="Execution mode (cron/on_demand/heal)")
    parser.add_argument("--finalize", action="store_true", help="Finalize-only mode: enrich + report + cleanup from DB (no collection)")
    parser.add_argument("--no-finalize", action="store_true", help="Skip finalize step (collection only)")
    parser.add_argument("--force", action="store_true", help="Force full scrape (skip freshness check)")
    parser.add_argument(
        "--stores-filter",
        type=str,
        default=None,
        help="Filtrar coleta para lojas (case-insensitive, substring). Nomes separados por virgula.",
    )
    return parser.parse_args()


PriceDict = dict[str, Any]


def generate_report_html(products: list[PriceDict], ingredients: list[dict[str, Any]]) -> str:
    import html as _html
    from collections import defaultdict

    by_ingredient: dict[str, list[PriceDict]] = defaultdict(list)
    for p in products:
        by_ingredient[p["ingredient_id"]].append(p)

    rows = ""
    for ing_name, prices in sorted(by_ingredient.items()):
        best = min(
            prices,
            key=lambda x: x["normalized"]["price_per_kg"]
            if isinstance(x.get("normalized"), dict)
            else 999999,
        )
        raw_norm = best.get("normalized")
        norm = raw_norm if isinstance(raw_norm, dict) else {}
        price_kg = norm.get("price_per_kg", 0)
        unique_stores = len({p.get("store_id", "") for p in prices})
        safe_ing = _html.escape(ing_name)
        safe_store = _html.escape(best["store_name"])
        rows += f"""
        <tr>
            <td><b>{safe_ing}</b></td>
            <td>{safe_store}</td>
            <td>R$ {best["raw_price"]:.2f}</td>
            <td>R$ {price_kg:.2f}/kg</td>
            <td>{unique_stores}</td>
        </tr>"""

    today = date.today().isoformat()
    html = f"""
    <html><body>
    <h2> CustoDoce - Relatorio Diario</h2>
    <p>Data: {today} | Total de itens: {len(products)}</p>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse">
        <tr style="background:#f0f0f0">
            <th>Ingrediente</th><th>Melhor Preco</th><th>Valor</th><th>R$/kg</th><th>Fontes</th>
        </tr>
        {rows}
    </table>
    <hr>
    <p><small>Enviado automaticamente pelo CustoDoce</small></p>
    </body></html>
    """
    return html


# (tier, collector_method, needs_ingredients)
# Tier 1  - PDF Direto (atacadistas) + SP capital + Extra + Pao + Roldao
# Tier 2a - E-commerce SP (VTEX / site proprio)
# Tier 2b - Atacado Fisico SP (manual / planilha) - sem coleta automatica
# Tier 3  - Agregadores (Tiendeo, Guiato, Facebook)
TIER_PLAN: list[tuple[str, str, bool]] = [
    ("1", "collect_tier1_pdfs", True),
    ("1", "collect_tier1_api_flyers", True),
    ("1", "collect_extra_flyers", True),
    ("1", "collect_pao_flyers", True),
    ("1", "collect_roldao_flyer", True),
    ("1", "collect_giga_flyer", True),
    ("1", "process_ocr_queue", False),
    ("2a", "collect_tier2_vtex", True),
    ("2a", "collect_vipcommerce", True),
    ("2a", "collect_carrefour", True),
    ("2a", "collect_tier2_js", True),
    ("3", "collect_tier3_websites", True),
    ("3", "collect_aggregators_ssr", False),
    ("3", "collect_aggregators_js", False),
    ("3", "collect_facebook_flyers", True),
]


def _collect(args: Namespace, collector: Any, ingredients: list[Ingredient]) -> list[dict[str, Any]]:
    """Run only the collectors for the requested --tier (or all if None).

    Each collector upserts directly to Supabase, so splitting collection
    across parallel tier jobs is safe: the shared DB receives every tier's
    data. Previously main() ignored --tier and ran the full pipeline N times
    (once per matrix entry), causing 4x redundant I/O, emails and cleanups.
    """
    # Reset session-level LLM exhaustion flag at start of each scrape
    from parsers.llm_strategies import reset_llm_exhausted
    reset_llm_exhausted()

    collected: list[list[dict[str, Any]]] = []
    for tier, method, needs_ing in TIER_PLAN:
        if args.tier and tier != args.tier:
            continue

        # Circuit breaker check
        cb = _get_circuit_breaker(f"{tier}_{method}")
        if not cb.is_available():
            logger.warning("circuit_breaker_skipping", tier=tier, method=method, state=cb.state)
            continue

        fn = getattr(collector, method)
        try:
            result = fn(ingredients) if needs_ing else fn()
            cb.record_success()
        except Exception as e:
            logger.error("collector_error", tier=tier, method=method, error=str(e))
            cb.record_failure()
            result = []
        if isinstance(result, list):
            collected.append(result)
            logger.info(f"{method}_collected", count=len(result))
        else:
            logger.info(f"{method}_done", result=result)
    return [p for sub in collected for p in sub]


def _pull_from_db() -> list[dict[str, Any]]:
    """Pull all current prices from Supabase for finalize-only mode."""
    try:
        from services.price_repository import get_latest_prices

        prices: list[dict[str, Any]] = get_latest_prices(valid_only=True, limit=2000)
        logger.info("finalize_pulled_from_db", count=len(prices))
        return prices
    except Exception as e:
        logger.error("finalize_db_pull_failed", error=str(e))
        return []


def _run_with_timeout(fn: Callable[[], Any], timeout: int, label: str) -> Any:
    """Roda fn num thread daemon e aborta o espero apos `timeout`s.

    Nao mata o thread (nao e seguro), mas libera o finalize para concluir
    e soltar o scrape lock mesmo se fn travar/lento (ex.: N+1 queries ou
    notificacoes externas sob carga).
    """
    holder: dict[str, Any] = {}

    def _target() -> None:
        try:
            holder["value"] = fn()
        except Exception as e:  # noqa: BLE001
            holder["error"] = str(e)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        logger.warning("timeout_ignored", label=label, timeout=timeout)
        return None
    if "error" in holder:
        logger.warning("error_ignored", label=label, error=holder["error"])
        return None
    return holder.get("value")


def _finalize(all_products: list[dict[str, Any]], ingredients: list[Ingredient], args: Namespace) -> None:
    """Enrich + snapshot + report + cleanup. Runs once per scrape run."""
    try:
        pi = price_intelligence.PriceIntelligence()
        all_products = pi.enrich_prices(all_products)
        anomalies = sum(1 for p in all_products if p.get("ai_anomaly", {}).get("is_anomaly"))
        offers = sum(1 for p in all_products if "OFERTA_REAL" in p.get("ai_tags", []))
        logger.info("price_intelligence_results", analyzed=len(all_products), anomalies=anomalies, offers=offers)
    except Exception as e:
        logger.warning("price_intelligence_error", error=str(e))

    # Auto-promote discovered stores with >=2 matched products
    try:
        from services.store_registry import auto_promote_discovered_stores
        promoted = auto_promote_discovered_stores(min_matched_products=2)
        if promoted:
            logger.info("auto_promote_completed", promoted=promoted)
    except Exception as e:
        logger.warning("auto_promote_error", error=str(e))

    snapshot = {
        "collected_at": datetime.now(UTC).isoformat(),
        "total_prices": len(all_products),
        "ingredients_found": len({p["ingredient_id"] for p in all_products}),
    }
    snapshot_path = DATA_DIR / "prices_latest.json"
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    if all_products and not args.dry_run:
        try:
            report_html = price_analytics.generate_report_html(cast("list[PriceEntry]", all_products), ingredients)
            email_service.send_daily_report(report_html=report_html)
            logger.info("daily_report_sent")
        except Exception as e:
            logger.warning("daily_report_error", error=str(e))

    # Cleanups só rodam em modo real
    if not args.dry_run:
        for name, fn, days in [
            ("prices", price_service.cleanup_old_prices, 90),
            ("logs", price_service.cleanup_old_logs, 30),
            ("flyers", flyer_service.cleanup_old_flyers, 60),
            ("flyers_all", price_service.cleanup_old_flyers_all, 180),
            ("review_resolved", price_service.cleanup_resolved_review_items, 30),
        ]:
            try:
                result = fn(retention_days=days)
                logger.info("cleanup_executed", target=name, result=result)
            except Exception as e:
                logger.warning("cleanup_error", target=name, error=str(e))

        try:
            result = flyer_service.cleanup_non_food_flyers()
            logger.info("cleanup_non_food_flyers_executed", result=result)
        except Exception as e:
            logger.warning("cleanup_non_food_flyers_error", error=str(e))

        try:
            rejected_count = price_service.auto_reject_stale_review_items(max_age_days=14, min_confidence=0.70)
            logger.info("cleanup_review_queue_executed", rejected_count=rejected_count)
        except Exception as e:
            logger.warning("cleanup_review_queue_error", error=str(e))

        # FASE 6: Proactive Alerts (só em modo real) — com timeout p/ nao
        # travar o finalize (e o scrape lock) sob carga de N+1 queries/notify.
        try:
            from services import alert_service

            _run_with_timeout(alert_service.process_proactive_alerts, 300, "process_proactive_alerts")
        except Exception as e:
            logger.error("proactive_alerts_failed", error=str(e))
    else:
        logger.info("dry_run_skip_side_effects")


def main(args: Namespace | None = None) -> None:
    if args is None:
        args = parse_args()
    with otel.tracer.start_as_current_span("main_collection_loop"):
        logger.info("custodoce_collection_start", start_time=datetime.now().isoformat())

        ingredients = collector.load_ingredients()
        logger.info("ingredients_loaded", count=len(ingredients))

        # Limpar dados de teste orfaos (Cleanup Store, _test_, e2e_, test _)
        # antes de iniciar a coleta para evitar scraper warnings por lixo
        # residual de execucoes de integration tests.
        try:
            cleaned = cleanup_test_data()
            total_cleaned = sum(cleaned.values())
            if total_cleaned > 0:
                logger.info("cleanup_test_data_executed", **cleaned)
        except Exception as e:
            logger.warning("cleanup_test_data_error", error=str(e))

        try:
            n = sync_store_fields()
            m = sync_scrape_frequencies()
            u = sync_store_units()
            logger.info("store_fields_synced", updated=n, frequencies=m, units=u)
        except Exception as e:
            logger.warning("sync_store_fields_error", error=str(e))

        if args.force:
            os.environ["CUSTODOCE_FORCE_SCRAPE"] = "1"
            logger.info("force_mode_enabled", msg="Freshness check bypassed for all stores")

        if args.stores_filter:
            os.environ["CUSTODOCE_STORES_FILTER"] = args.stores_filter
            logger.info("stores_filter_enabled", filter=args.stores_filter)

        # ── Collection dispatch (filtered by --tier) ──
        collect_mode = args.tier is not None
        full_local = (args.tier is None and not args.finalize and not args.no_finalize)
        run_collection = collect_mode or full_local
        run_finalize = args.finalize or full_local

        all_products: list[dict[str, Any]] = []
        if run_collection:
            all_products = _collect(args, collector, ingredients)
            logger.info("collection_done", total=len(all_products))

            # Auto-discover stores from aggregator flyers
            try:
                store_registry.discover_stores_from_flyers()
                logger.info("store_discovery_completed")
            except Exception as e:
                logger.warning("store_discovery_error", error=str(e))
        else:
            logger.info("collection_skipped", reason="--finalize (finalize-only mode)")

        # ── Finalize (enrich + report + cleanup) ── runs once ──
        if run_finalize:
            if not run_collection:
                # Finalize-only mode: pull all prices from DB (parallel tiers
                # already upserted their data).
                all_products = _pull_from_db()
            _finalize(all_products, ingredients, args)
        else:
            logger.info("finalize_skipped", reason="--no-finalize")

        logger.info("custodoce_collection_finished", end_time=datetime.now().isoformat())


if __name__ == "__main__":
    main()
