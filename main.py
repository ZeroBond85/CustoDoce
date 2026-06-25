import html as _html
import json
import logging
import re
import sys
from contextlib import suppress
from datetime import datetime, date, timezone
from inspect import signature
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scrapers.flyer_scraper import FlyerScraper
from scrapers.extra_flyer_scraper import ExtraFlyerScraper
from scrapers.pao_flyer_scraper import PaoFlyerScraper
from scrapers.vtex_scraper import VtexScraper
from scrapers.website_scraper import WebsiteScraper
from scrapers.carrefour_scraper import CarrefourScraper
from scrapers.tenda_api_scraper import TendaApiScraper
from scrapers.roldao_api_scraper import RoldaoApiScraper
from scrapers.max_api_scraper import MaxApiScraper
from scrapers.aggregator_scraper import TiendeoScraper
from scrapers.playwright_price_scraper import PlaywrightPriceScraper
from parsers.normalizer import normalize_price
from parsers.matcher import match_ingredient, rank_ingredients, clean_text, extract_all_keywords, has_ingredient_keyword
from parsers.brand_extractor import extract_brand
from services.price_service import upsert_price, insert_review_item, log_scraper_run, cleanup_old_prices, cleanup_old_logs, auto_reject_stale_review_items, _detect_promotion, _weekday_pt
from services.flyer_service import cleanup_old_flyers, cleanup_non_food_flyers
from services.flyer_service import upsert_flyer
from services.email_service import send_daily_report, send_scraper_error
from services.config_db import get_active_ingredients, get_active_stores
from services.supabase_client import get_service_client, get_supabase
from scripts.sync_all_store_fields import sync_store_fields, sync_scrape_frequencies

_auto_disable_threshold = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


def _upload_flyer_thumbnail(store_name: str, thumbnail_bytes: bytes) -> str:
    """Upload a PNG thumbnail to Supabase Storage and return the public URL."""
    try:
        client = get_service_client()
        safe_name = store_name.lower().replace(" ", "_").replace("/", "_")
        path = f"flyers/{safe_name}_{date.today().isoformat()}.png"
        client.storage.from_("thumbnails").upload(
            path=path,
            file=thumbnail_bytes,
            file_options={"content_type": "image/png", "upsert": "true"},
        )
        url = client.storage.from_("thumbnails").get_public_url(path)
        logger.info("[%s] Thumbnail uploaded: %s", store_name, path)
        return url
    except Exception as e:
        logger.warning("[%s] Thumbnail upload failed: %s", store_name, e)
        return ""

API_SCRAPER_MAP = {
    "tenda_api_scraper": TendaApiScraper,
    "roldao_api_scraper": RoldaoApiScraper,
    "max_api_scraper": MaxApiScraper,
}


def load_ingredients() -> list[dict]:
    return get_active_ingredients()


def load_stores() -> list[dict]:
    all_stores = get_active_stores()
    if not all_stores:
        return []
    # Load enabled store IDs from scrape_frequencies
    client = get_supabase()
    freq = client.table("scrape_frequencies").select("store_id").eq("enabled", True).execute()
    enabled_ids = {f["store_id"] for f in (freq.data or [])}
    if not enabled_ids:
        return all_stores  # fallback: se tabela vazia, usa todas
    return [s for s in all_stores if s.get("id") in enabled_ids]


def _extract_validity_from_product(product_text: str) -> str:
    m = re.search(r"(?:valido?\s*(?:ate?|até)?\s*:?\s*[\d]{2}/[\d]{2}(?:/[\d]{2,4})?)", product_text, re.I)
    if m:
        return m.group(0)
    m2 = re.search(r"(?:ate?|até)\s*[\d]{2}/[\d]{2}(?:/[\d]{2,4})?", product_text, re.I)
    if m2:
        return m2.group(0)
    return ""


def build_product_entry(
    store: dict,
    ingredient: dict,
    raw_product: str,
    raw_price: float,
    raw_unit: str,
    confidence: float,
    validity_raw: str = "",
    brand: str = "",
) -> dict:
    normalized = normalize_price(raw_price, raw_unit)
    validity = validity_raw or _extract_validity_from_product(raw_product)
    brand = brand or extract_brand(raw_product, ingredient)
    return {
        "ingredient_id": ingredient["canonical_name"],
        "store_id": store.get("id") or store["name"].lower().replace(" ", "_"),
        "source": store.get("type", "automated"),
        "store_name": store["name"],
        "raw_product": raw_product,
        "raw_price": raw_price,
        "raw_unit": raw_unit,
        "validity_raw": validity,
        "collected_weekday": _weekday_pt(datetime.now()),
        "is_promotion": _detect_promotion(raw_product, raw_unit),
        "tier": store.get("tier", 3),
        "confidence": confidence,
        "normalized": normalized.to_dict() if normalized else None,
        "city": store.get("cities", [""])[0] if isinstance(store.get("cities"), list) else store.get("city", ""),
        "logistics": store.get("logistics", "pickup_local"),
        "brand": brand,
    }


_keyword_cache: tuple[int, set] | None = None

def _get_ingredient_keywords(ingredients: list[dict]) -> set:
    global _keyword_cache
    ing_id = id(ingredients)
    if _keyword_cache is not None and _keyword_cache[0] == ing_id:
        return _keyword_cache[1]
    keywords = extract_all_keywords(ingredients)
    _keyword_cache = (ing_id, keywords)
    return keywords


def process_price_match(
    store: dict,
    product_text: str,
    raw_price: float,
    raw_unit: str,
    ingredients: list[dict],
    validity_raw: str = "",
    brand: str = "",
    image_url: str = "",
    source_url: str = "",
) -> dict | None:
    keywords = _get_ingredient_keywords(ingredients)
    if not has_ingredient_keyword(product_text, keywords):
        return None

    ingredient, score, match_type = match_ingredient(product_text, ingredients)
    if ingredient and score >= 80.0:
        entry = build_product_entry(
            store, ingredient, product_text,
            raw_price, raw_unit, score / 100.0,
            validity_raw=validity_raw,
            brand=brand,
        )
        upsert_price(entry)
        return entry

    if score >= 55.0:
        candidates = rank_ingredients(product_text, ingredients, top_n=3)
        suggestions = [c[0]["canonical_name"] for c in candidates if c[1] >= 55.0]
        validity = validity_raw or _extract_validity_from_product(product_text)

        # Build detailed match reason
        match_type = ""
        match_reason = ""
        if candidates:
            top = candidates[0]
            top_ing, top_score, top_type, top_term = top
            match_type = top_type

            # Type label in PT
            type_labels = {
                "proximo_nome": "semelhante ao nome do ingrediente",
                "proximo_apelido": "semelhante a um apelido do ingrediente",
                "exato": "exato",
                "contido": "nome do ingrediente contido no produto",
            }
            type_label = type_labels.get(top_type, top_type)

            # Product text analysis
            product_words = set(clean_text(product_text).split())
            canonical_words = set(clean_text(top_ing["canonical_name"]).split())
            unmatched_words = product_words - canonical_words

            match_reason = (
                f"Tipo: {type_label} | "
                f"Score: {top_score:.0f}% | "
                f"Candidato: '{top_ing['canonical_name']}' | "
                f"Termo match: '{top_term}'"
            )
            if unmatched_words:
                match_reason += f" | Palavras não matcheadas: {', '.join(sorted(unmatched_words))}"
        else:
            match_reason = f"Score {score:.0f}% - nenhum candidato acima de 55%"

        # Build top 3 summary for UI
        top3_summary = []
        for c in candidates:
            top3_summary.append({
                "canonical_name": c[0]["canonical_name"],
                "score": c[1],
                "match_type": c[2],
                "matched_term": c[3],
            })

        if not brand and candidates:
            brand = extract_brand(product_text, candidates[0][0])

        review_item = {
            "raw_product": product_text,
            "raw_price": raw_price,
            "raw_unit": raw_unit,
            "store_name": store["name"],
            "source": store.get("type", "automated"),
            "confidence": score / 100.0,
            "suggestions": suggestions,
            "validity_raw": validity,
            "brand": brand,
            "image_url": image_url,
            "source_url": source_url,
            "match_reason": match_reason,
            "match_type": match_type,
            "top3": top3_summary,
        }
        try:
            insert_review_item(review_item)
        except Exception as e:
            logger.warning("Review queue error: %s", e)

    return None


def _auto_disable_if_needed(store_name: str, threshold: int = 3):
    """Auto-desativa loja se ultimos N logs sao todos erros."""
    try:
        client = get_service_client()
        logs = (
            client.table("scraping_logs")
            .select("status")
            .eq("store_name", store_name)
            .order("started_at", desc=True)
            .limit(threshold)
            .execute()
        )
        if not logs.data or len(logs.data) < threshold:
            return
        if all(log["status"] in ("error", "failed") for log in logs.data):
            store = (
                client.table("stores")
                .select("id, is_active")
                .eq("name", store_name)
                .single()
                .execute()
            )
            if store.data and store.data.get("is_active") is not False:
                client.table("stores").update({"is_active": False}).eq("id", store.data["id"]).execute()
                logger.warning("[AUTO-DISABLE] %s desativada apos %d falhas consecutivas", store_name, threshold)
    except Exception as e:
        logger.debug("auto-disable check failed for %s: %s", store_name, e)


def _collect_prices(
    stores: list[dict],
    scraper_cls: type,
    ingredients: list[dict],
    label: str,
) -> list[dict]:
    all_products = []
    for store in stores:
        store_name = store.get("name", "unknown")
        try:
            with scraper_cls(store) as scraper:
                sig = signature(scraper.run)
                raw_products = scraper.run(ingredients) if 'ingredients' in sig.parameters else scraper.run()

            if hasattr(scraper, '_thumbnail') and scraper._thumbnail:
                try:
                    thumb_url = _upload_flyer_thumbnail(store_name, scraper._thumbnail)
                    if thumb_url:
                        upsert_flyer({
                            "store_name": store_name,
                            "region": store.get("region", ""),
                            "city": store.get("city", ""),
                            "flyer_title": f"Panfleto {date.today().strftime('%d/%m/%Y')}",
                            "image_url": thumb_url,
                            "source": "pdf_scrape",
                        })
                except Exception as e:
                    logger.debug("[%s] Flyer record save failed: %s", store_name, e)

            if not raw_products:
                logger.info("[%s] No products found", store_name)
                log_scraper_run(store_name, "completed", 0, 0)
                continue

            matched = 0
            for prod in raw_products:
                entry = process_price_match(
                    store,
                    prod.get("product", ""),
                    prod.get("price", 0),
                    prod.get("unit", ""),
                    ingredients,
                    validity_raw=prod.get("validity_raw", ""),
                    brand=prod.get("brand", ""),
                    source_url=prod.get("source_url", ""),
                )
                if entry:
                    matched += 1
                    all_products.append(entry)

            logger.info("[%s] %d products, %d matched", store_name, len(raw_products), matched)
            log_scraper_run(store_name, "completed", len(raw_products), matched)

        except Exception as e:
            logger.error("[%s] %s: %s", label, store_name, e)
            log_scraper_run(store_name, "error", 0, 0, str(e))
            with suppress(Exception):
                send_scraper_error(store_name, str(e))
            _auto_disable_if_needed(store_name)

    return all_products


def _collect_flyers(
    stores: list[dict],
    scraper_cls: type | None,
    label: str,
    run_fn=None,
) -> list[dict]:
    all_flyers = []
    for store in stores:
        store_name = store.get("name", "unknown")
        try:
            if scraper_cls:
                with scraper_cls(store) as scraper:
                    entries = scraper.run([]) if hasattr(scraper, 'run') else []
            elif run_fn:
                entries = run_fn(store)
            else:
                continue

            if not entries:
                logger.info("[%s] No flyer entries found", store_name)
                continue

            saved = 0
            for entry in entries:
                try:
                    if "store_name" not in entry:
                        entry["store_name"] = store_name
                    if "region" not in entry:
                        entry["region"] = store.get("city", store.get("zone", ""))
                    if "image_url" not in entry or not entry.get("image_url"):
                        continue
                    upsert_flyer(entry)
                    saved += 1
                except Exception as e:
                    logger.warning("Flyer save error: %s", e)

            logger.info("[%s] %d flyer entries, %d saved", store_name, len(entries), saved)

        except Exception as e:
            logger.error("[%s] %s: %s", label, store_name, e)
            with suppress(Exception):
                send_scraper_error(store_name, str(e))

    return all_flyers


def collect_tier1_pdfs(ingredients: list[dict]) -> list[dict]:
    today = date.today()
    weekday = today.strftime("%A").lower()
    stores = []
    for s in [x for x in load_stores() if x.get("tier") == 1 and x.get("type") == "pdf_flyer"]:
        pd = s.get("publish_day") or "wednesday"
        if weekday in (pd if isinstance(pd, str) else [pd]) or weekday == "thursday":
            stores.append(s)
    return _collect_prices(stores, FlyerScraper, ingredients, "PDF")


def collect_extra_flyers(ingredients: list[dict]) -> list[dict]:
    stores = [s for s in load_stores() if s.get("scraper") == "extra_flyer_scraper" and s.get("type") == "extra_flyer"]
    return _collect_prices(stores, ExtraFlyerScraper, ingredients, "ExtraFlyer")


def collect_pao_flyers(ingredients: list[dict]) -> list[dict]:
    stores = [s for s in load_stores() if s.get("scraper") == "pao_flyer_scraper" and s.get("type") == "pao_flyer"]
    return _collect_prices(stores, PaoFlyerScraper, ingredients, "PaoFlyer")


def collect_tier1_api_flyers(ingredients: list[dict]) -> list[dict]:
    stores = [s for s in load_stores() if s.get("tier") == 1 and s.get("type") == "api_flyer"]
    return _collect_flyers(stores, None, "API-Flyer", run_fn=_run_api_flyer_scraper)


def _run_api_flyer_scraper(store: dict) -> list[dict]:
    scraper_name = (store.get("scraper") or "").strip().lower()
    if not scraper_name:
        logger.warning("[%s] No scraper configured", store.get("name", "unknown"))
        return []
    cls = API_SCRAPER_MAP.get(scraper_name)
    if cls is None:
        logger.warning("[%s] No API scraper class found for '%s'", store.get("name", "unknown"), scraper_name)
        return []
    store_name = store.get("name", "unknown")
    region = store.get("city", store.get("zone", ""))
    with cls(store) as scraper:
        entries = scraper.run([])
    for entry in entries:
        if "store_name" not in entry:
            entry["store_name"] = store_name
        if "region" not in entry:
            entry["region"] = region
        if "source" not in entry:
            entry["source"] = f"api_{scraper_name}"
    return entries


def collect_tier2_vtex(ingredients: list[dict]) -> list[dict]:
    stores = [s for s in load_stores() if s.get("scraper") == "vtex_scraper" and s.get("type") == "vtex_api"]
    return _collect_prices(stores, VtexScraper, ingredients, "VTEX")


def collect_tier3_websites(ingredients: list[dict]) -> list[dict]:
    stores = [s for s in load_stores() if s.get("scraper") == "website_scraper" and s.get("type") == "website_catalog"]
    return _collect_prices(stores, WebsiteScraper, ingredients, "Website")


def collect_carrefour(ingredients: list[dict]) -> list[dict]:
    stores = [s for s in load_stores() if s.get("scraper") == "carrefour_scraper" and s.get("type") == "website_catalog"]
    return _collect_prices(stores, CarrefourScraper, ingredients, "Carrefour")


def collect_tier2_js(ingredients: list[dict]) -> list[dict]:
    stores = [s for s in load_stores() if s.get("scraper") == "playwright_price_scraper" and s.get("type") == "website_js"]
    return _collect_prices(stores, PlaywrightPriceScraper, ingredients, "Playwright")


def collect_aggregators_ssr() -> list[dict]:
    stores = [s for s in load_stores() if s.get("scraper") == "aggregator_scraper" and s.get("type") == "aggregator"]
    return _collect_flyers(stores, None, "SSR", run_fn=_run_ssr_scraper)


def _run_ssr_scraper(store: dict) -> list[dict]:
    scraper = TiendeoScraper(store)
    return scraper.run()


def collect_aggregators_js() -> list[dict]:
    stores = [s for s in load_stores() if s.get("scraper") == "playwright_scraper" and s.get("type") == "aggregator_js"]
    return _collect_flyers(stores, None, "JS", run_fn=_run_js_scraper)


def _run_js_scraper(store: dict) -> list[dict]:
    from scrapers.playwright_scraper import PlaywrightAggregatorScraper
    scraper = PlaywrightAggregatorScraper(store)
    return scraper.run()


def process_ocr_queue() -> int:
    from services.flyer_service import get_pending_flyers, mark_processed, mark_failed
    from scrapers.flyer_parser import extract_lines_from_text, parse_flyer_lines
    import httpx

    pending = get_pending_flyers(limit=10)
    if not pending:
        return 0

    ingredients = load_ingredients()
    processed = 0
    for flyer in pending:
        try:
            img_url = flyer["image_url"]
            if img_url and not img_url.startswith(("http://", "https://")):
                img_url = "https://" + img_url
            resp = httpx.get(img_url, timeout=30)
            if resp.status_code != 200:
                mark_failed(flyer["id"])
                continue

            img_bytes = resp.content
            if len(img_bytes) < 1000:
                mark_failed(flyer["id"])
                continue

            from scrapers.ocr import ocr_image_bytes
            text = ocr_image_bytes(img_bytes)
            if not text:
                mark_failed(flyer["id"])
                continue

            lines = extract_lines_from_text(text)
            products = parse_flyer_lines(lines)

            matched = 0
            for prod in products:
                entry = process_price_match(
                    store={"name": flyer["store_name"], "type": flyer.get("source", "aggregator"), "tier": 3},
                    product_text=prod.get("product", ""),
                    raw_price=prod.get("price", 0),
                    raw_unit=prod.get("unit", ""),
                    ingredients=ingredients,
                    validity_raw=prod.get("validity_raw", ""),
                    image_url=flyer.get("image_url", ""),
                    source_url=prod.get("source_url", flyer.get("source_url", "")),
                )
                if entry:
                    matched += 1

            mark_processed(flyer["id"], products_count=matched)
            processed += 1

        except Exception as e:
            logger.error("[OCR] Error processing flyer %s: %s", flyer.get("id"), e)
            with suppress(Exception):
                mark_failed(flyer["id"])

    return processed


def main():
    logger.info("=" * 50)
    logger.info("CustoDoce - Coleta de Precos")
    logger.info("Inicio: %s", datetime.now().isoformat())
    logger.info("=" * 50)

    ingredients = load_ingredients()
    logger.info("%d ingredientes carregados", len(ingredients))

    try:
        n = sync_store_fields()
        m = sync_scrape_frequencies()
        logger.info("Store fields synced: %d updated, %d frequencies", n, m)
    except Exception as e:
        logger.warning("Erro sync store fields (nao bloqueante): %s", e)

    logger.info("Coletando Tier 1 (PDFs)...")
    tier1_products = collect_tier1_pdfs(ingredients)
    logger.info("-> %d precos coletados", len(tier1_products))

    logger.info("Coletando Extra Folheteria...")
    extra_products = collect_extra_flyers(ingredients)
    logger.info("-> %d precos coletados", len(extra_products))

    logger.info("Coletando Pao de Acucar Fresh...")
    pao_products = collect_pao_flyers(ingredients)
    logger.info("-> %d precos coletados", len(pao_products))

    logger.info("Coletando Tier 1 (API Flyers)...")
    tier1_flyers = collect_tier1_api_flyers(ingredients)
    logger.info("-> %d folhetos coletados", len(tier1_flyers))

    logger.info("Processando OCR dos flyers coletados...")
    ocr_processed = process_ocr_queue()
    logger.info("-> %d flyers processados via OCR", ocr_processed)

    logger.info("Coletando Tier 2a (VTEX)...")
    tier2_products = collect_tier2_vtex(ingredients)
    logger.info("-> %d precos coletados", len(tier2_products))

    logger.info("Coletando Tier 3 (Websites)...")
    tier3_products = collect_tier3_websites(ingredients)
    logger.info("-> %d precos coletados", len(tier3_products))

    logger.info("Coletando Carrefour...")
    carrefour_products = collect_carrefour(ingredients)
    logger.info("-> %d precos coletados", len(carrefour_products))

    logger.info("Coletando Tier 2 JS (Playwright)...")
    js_products = collect_tier2_js(ingredients)
    logger.info("-> %d precos coletados", len(js_products))

    logger.info("Coletando Agregadores SSR...")
    ssr_flyers = collect_aggregators_ssr()
    logger.info("-> %d folhetos coletados", len(ssr_flyers))

    all_products = tier1_products + extra_products + pao_products + tier2_products + tier3_products + carrefour_products + js_products
    snapshot = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "total_prices": len(all_products),
        "ingredients_found": len({p["ingredient_id"] for p in all_products}),
    }
    snapshot_path = DATA_DIR / "prices_latest.json"
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    if all_products:
        try:
            report_html = generate_report_html(all_products, ingredients)
            send_daily_report(report_html=report_html)
            logger.info("Relatorio enviado por email")
        except Exception as e:
            logger.warning("Erro ao enviar email: %s", e)

    for name, fn, days in [
        ("prices", cleanup_old_prices, 90),
        ("logs", cleanup_old_logs, 30),
        ("flyers", cleanup_old_flyers, 60),
    ]:
        try:
            result = fn(retention_days=days)
            logger.info("Cleanup %s: %s", name, result)
        except Exception as e:
            logger.warning("Erro cleanup %s: %s", name, e)

    try:
        result = cleanup_non_food_flyers()
        logger.info("Cleanup non-food flyers: %s", result)
    except Exception as e:
        logger.warning("Erro cleanup non-food flyers: %s", e)

    try:
        result = auto_reject_stale_review_items(max_age_days=7, min_confidence=0.6)
        logger.info("Cleanup review queue (stale auto-reject): %d rejeitados", result)
    except Exception as e:
        logger.warning("Erro cleanup review queue: %s", e)

    logger.info("Coleta concluida: %s", datetime.now().isoformat())


def generate_report_html(products: list[dict], ingredients: list[dict]) -> str:
    by_ingredient = {}
    for p in products:
        ing = p["ingredient_id"]
        if ing not in by_ingredient:
            by_ingredient[ing] = []
        by_ingredient[ing].append(p)

    rows = ""
    for ing_name, prices in sorted(by_ingredient.items()):
        best = min(prices, key=lambda x: (x.get("normalized") or {}).get("price_per_kg", 999999))
        norm = best.get("normalized") or {}
        price_kg = norm.get("price_per_kg", 0)
        unique_stores = len({p.get("store_id", "") for p in prices})

        safe_ing = _html.escape(ing_name)
        safe_store = _html.escape(best['store_name'])
        rows += f"""
        <tr>
            <td><b>{safe_ing}</b></td>
            <td>{safe_store}</td>
            <td>R$ {best['raw_price']:.2f}</td>
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


if __name__ == "__main__":
    main()
