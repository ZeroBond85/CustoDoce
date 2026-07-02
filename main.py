"""
CustoDoce - Main Orchestrator
Coordinates collection, cleaning, intelligence, and reporting.
"""

import json
from services.logger import logger
from datetime import datetime, date, UTC
from pathlib import Path

from services import collector, price_service, price_intelligence, price_analytics, flyer_service, email_service, otel
from scripts.sync_all_store_fields import sync_store_fields, sync_scrape_frequencies


DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


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
            key=lambda x: (
                x.get("normalized") if isinstance(x.get("normalized"), dict) else {}
            ).get("price_per_kg", 999999),
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


def main():
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

        logger.info("collecting_tier1_pdfs")
        tier1_products = collector.collect_tier1_pdfs(ingredients)
        logger.info("tier1_pdfs_collected", count=len(tier1_products))

        logger.info("collecting_extra_flyers")
        extra_products = collector.collect_extra_flyers(ingredients)
        logger.info("extra_flyers_collected", count=len(extra_products))

        logger.info("collecting_pao_flyers")
        pao_products = collector.collect_pao_flyers(ingredients)
        logger.info("pao_flyers_collected", count=len(pao_products))

        logger.info("collecting_tier1_api_flyers")
        tier1_flyers = collector.collect_tier1_api_flyers(ingredients)
        logger.info("tier1_api_flyers_collected", count=len(tier1_flyers))

        logger.info("processing_ocr_queue")
        ocr_processed = collector.process_ocr_queue()
        logger.info("ocr_processed_count", count=ocr_processed)

        logger.info("collecting_tier2_vtex")
        tier2_products = collector.collect_tier2_vtex(ingredients)
        logger.info("tier2_vtex_collected", count=len(tier2_products))

        logger.info("collecting_tier3_websites")
        tier3_products = collector.collect_tier3_websites(ingredients)
        logger.info("tier3_websites_collected", count=len(tier3_products))

        logger.info("collecting_carrefour")
        carrefour_products = collector.collect_carrefour(ingredients)
        logger.info("carrefour_collected", count=len(carrefour_products))

        logger.info("collecting_tier2_js")
        js_products = collector.collect_tier2_js(ingredients)
        logger.info("tier2_js_collected", count=len(js_products))

        logger.info("collecting_aggregators_ssr")
        ssr_flyers = collector.collect_aggregators_ssr()
        logger.info("aggregators_ssr_collected", count=len(ssr_flyers))

        logger.info("collecting_roldao_flyer")
        roldao_products = collector.collect_roldao_flyer(ingredients)
        logger.info("roldao_flyer_collected", count=len(roldao_products))

        all_products = (
            tier1_products
            + extra_products
            + pao_products
            + tier2_products
            + tier3_products
            + carrefour_products
            + js_products
            + roldao_products
        )

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

        if all_products:
            try:
                report_html = price_analytics.generate_report_html(all_products, ingredients)
                email_service.send_daily_report(report_html=report_html)
                logger.info("daily_report_sent")
            except Exception as e:
                logger.warning("daily_report_error", error=str(e))

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

        # FASE 6: Proactive Alerts
        try:
            from services import alert_service

            alert_service.process_proactive_alerts()
        except Exception as e:
            logger.error("proactive_alerts_failed", error=str(e))

        logger.info("custodoce_collection_finished", end_time=datetime.now().isoformat())


if __name__ == "__main__":
    main()
