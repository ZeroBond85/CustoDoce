"""
CustoDoce - Main Orchestrator
Coordinates collection, cleaning, intelligence, and reporting.
"""

import json
import os
from argparse import ArgumentParser, Namespace
from datetime import UTC, date, datetime
from pathlib import Path

from scripts.sync_all_store_fields import sync_scrape_frequencies, sync_store_fields
from services import collector, email_service, flyer_service, otel, price_analytics, price_intelligence, price_service, store_registry
from services.logger import logger

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
    return parser.parse_args()


def generate_report_html(products: list[dict], ingredients: list[dict]) -> str:
    import html as _html
    from collections import defaultdict

    by_ingredient = defaultdict(list)
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


def _collect(args: Namespace, collector, ingredients: list) -> list[dict]:
    """Run only the collectors for the requested --tier (or all if None).

    Each collector upserts directly to Supabase, so splitting collection
    across parallel tier jobs is safe: the shared DB receives every tier's
    data. Previously main() ignored --tier and ran the full pipeline N times
    (once per matrix entry), causing 4x redundant I/O, emails and cleanups.
    """
    collected: list[list] = []
    for tier, method, needs_ing in TIER_PLAN:
        if args.tier and tier != args.tier:
            continue
        fn = getattr(collector, method)
        try:
            result = fn(ingredients) if needs_ing else fn()
        except Exception as e:
            logger.error("collector_error", tier=tier, method=method, error=str(e))
            result = []
        if isinstance(result, list):
            collected.append(result)
            logger.info(f"{method}_collected", count=len(result))
        else:
            logger.info(f"{method}_done", result=result)
    return [p for sub in collected for p in sub]


def _pull_from_db() -> list[dict]:
    """Pull all current prices from Supabase for finalize-only mode."""
    try:
        from services.price_repository import get_latest_prices

        prices = get_latest_prices(valid_only=True, limit=2000)
        logger.info("finalize_pulled_from_db", count=len(prices))
        return prices
    except Exception as e:
        logger.error("finalize_db_pull_failed", error=str(e))
        return []


def _finalize(all_products: list[dict], ingredients: list, args: Namespace) -> None:
    """Enrich + snapshot + report + cleanup. Runs once per scrape run."""
    try:
        pi = price_intelligence.PriceIntelligence()
        all_products = pi.enrich_prices(all_products)
        anomalies = sum(1 for p in all_products if p.get("ai_anomaly", {}).get("is_anomaly"))
        offers = sum(1 for p in all_products if "OFERTA_REAL" in p.get("ai_tags", []))
        logger.info("price_intelligence_results", analyzed=len(all_products), anomalies=anomalies, offers=offers)
    except Exception as e:
        logger.warning("price_intelligence_error", error=str(e))

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
            report_html = price_analytics.generate_report_html(all_products, ingredients)
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
            result = price_service.auto_reject_stale_review_items(max_age_days=14, min_confidence=0.3)
            logger.info("cleanup_review_queue_executed", rejected_count=result)
        except Exception as e:
            logger.warning("cleanup_review_queue_error", error=str(e))

        # FASE 6: Proactive Alerts (só em modo real)
        try:
            from services import alert_service

            alert_service.process_proactive_alerts()
        except Exception as e:
            logger.error("proactive_alerts_failed", error=str(e))
    else:
        logger.info("dry_run_skip_side_effects")


def main(args: Namespace | None = None):
    if args is None:
        args = parse_args()
    with otel.tracer.start_as_current_span("main_collection_loop"):
        logger.info("custodoce_collection_start", start_time=datetime.now().isoformat())

        ingredients = collector.load_ingredients()
        logger.info("ingredients_loaded", count=len(ingredients))

        try:
            n = sync_store_fields()
            m = sync_scrape_frequencies()
            logger.info("store_fields_synced", updated=n, frequencies=m)
        except Exception as e:
            logger.warning("sync_store_fields_error", error=str(e))

        if args.force:
            os.environ["CUSTODOCE_FORCE_SCRAPE"] = "1"
            logger.info("force_mode_enabled", msg="Freshness check bypassed for all stores")

        # ── Collection dispatch (filtered by --tier) ──
        collect_mode = args.tier is not None
        full_local = (args.tier is None and not args.finalize and not args.no_finalize)
        run_collection = collect_mode or full_local
        run_finalize = args.finalize or full_local

        all_products: list[dict] = []
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
