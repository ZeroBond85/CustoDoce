import sys
import json
from datetime import datetime, date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from scrapers.base_flyer import BaseFlyerScraper
from scrapers.assai_flyer import AssaiFlyerScraper
from scrapers.atacadao_flyer import AtacadaoFlyerScraper
from scrapers.spani_flyer import SpaniFlyerScraper
from scrapers.mercadao_flyer import MercadaoFlyerScraper
from scrapers.tenda_flyer import TendaFlyerScraper
from scrapers.roldao_flyer import RoldaoFlyerScraper
from scrapers.sams_flyer import SamsFlyerScraper
from scrapers.makro_flyer import MakroFlyerScraper
from scrapers.max_flyer import MaxFlyerScraper
from scrapers.vtex_scraper import VtexScraper
from scrapers.website_scraper import WebsiteScraper
from scrapers.aggregator_scraper import TiendeoScraper
from scrapers.carrefour_scraper import CarrefourScraper
from parsers.normalizer import normalize_price
from parsers.matcher import match_ingredient
from services.price_service import upsert_price, insert_review_item
from services.flyer_service import upsert_flyer
from services.email_service import send_daily_report, send_scraper_error

CONFIG_DIR = Path("config")
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


def load_ingredients() -> list[dict]:
    path = CONFIG_DIR / "ingredients.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("ingredients", [])


def load_stores() -> list[dict]:
    path = CONFIG_DIR / "stores.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("stores", [])


def build_product_entry(
    store: dict,
    ingredient: dict,
    raw_product: str,
    raw_price: float,
    raw_unit: str,
    confidence: float,
) -> dict:
    normalized = normalize_price(raw_price, raw_unit)
    return {
        "ingredient_id": ingredient["canonical"],
        "store_id": store.get("id") or store["name"].lower().replace(" ", "_"),
        "source": store.get("type", "automated"),
        "store_name": store["name"],
        "raw_product": raw_product,
        "raw_price": raw_price,
        "raw_unit": raw_unit,
        "tier": store.get("tier", 3),
        "confidence": confidence,
        "normalized": normalized.to_dict() if normalized else None,
        "city": store.get("cities", [""])[0] if isinstance(store.get("cities"), list) else store.get("city", ""),
        "logistics": store.get("logistics", "pickup_local"),
    }


def process_price_match(
    store: dict,
    product_text: str,
    raw_price: float,
    raw_unit: str,
    ingredients: list[dict],
) -> dict | None:
    from parsers.matcher import rank_ingredients

    ingredient, score, match_type = match_ingredient(product_text, ingredients)
    if ingredient and score >= 80.0:
        entry = build_product_entry(
            store, ingredient, product_text,
            raw_price, raw_unit, score / 100.0,
        )
        upsert_price(entry)
        return entry

    if score >= 30.0:
        candidates = rank_ingredients(product_text, ingredients, top_n=3)
        suggestions = [c[0]["canonical"] for c in candidates if c[1] >= 30.0]
        review_item = {
            "raw_product": product_text,
            "raw_price": raw_price,
            "raw_unit": raw_unit,
            "store_name": store["name"],
            "source": store.get("type", "automated"),
            "confidence": score / 100.0,
            "suggestions": suggestions,
        }
        try:
            insert_review_item(review_item)
        except Exception as e:
            print(f"  Review queue error: {e}")

    return None


SCRAPER_MAP = {
    "assai_flyer": AssaiFlyerScraper,
    "atacadao_flyer": AtacadaoFlyerScraper,
    "spani_flyer": SpaniFlyerScraper,
    "mercadao_flyer": MercadaoFlyerScraper,
    "tenda_flyer": TendaFlyerScraper,
    "roldao_flyer": RoldaoFlyerScraper,
    "sams_flyer": SamsFlyerScraper,
    "makro_flyer": MakroFlyerScraper,
    "max_flyer": MaxFlyerScraper,
}


def _get_flyer_scraper(store: dict) -> BaseFlyerScraper:
    scraper_name = store.get("scraper", "")
    cls = SCRAPER_MAP.get(scraper_name, BaseFlyerScraper)
    return cls(store)


def collect_tier1_pdfs(ingredients: list[dict]) -> list[dict]:
    stores = [s for s in load_stores() if s.get("tier") == 1]
    all_products = []

    for store in stores:
        try:
            scraper = _get_flyer_scraper(store)
            today = date.today()

            # Only run on publish day or next day
            weekday = today.strftime("%A").lower()
            publish_day = store.get("publish_day", "wednesday")
            if weekday not in (publish_day, "thursday"):
                continue

            products = scraper.run(today)
            if not products:
                print(f"[{store['name']}] No new products found (cached or empty)")
                continue

            matched = 0
            for prod in products:
                entry = process_price_match(
                    store,
                    prod.get("product", ""),
                    prod.get("price", 0),
                    prod.get("unit", ""),
                    ingredients,
                )
                if entry:
                    matched += 1
                    all_products.append(entry)

            print(f"[{store['name']}] Found {len(products)} products, matched {matched}")

        except Exception as e:
            print(f"[{store['name']}] Error: {e}")
            try:
                send_scraper_error(store["name"], str(e))
            except Exception:
                pass

    return all_products


def collect_tier2_vtex(ingredients: list[dict]) -> list[dict]:
    stores = [
        s for s in load_stores()
        if s.get("scraper") == "vtex_scraper"
        and s.get("type") == "vtex_api"
    ]
    all_products = []

    for store in stores:
        try:
            scraper = VtexScraper(store)
            raw_products = scraper.run(ingredients)
            if not raw_products:
                print(f"[{store['name']}] No products found")
                continue

            matched = 0
            for prod in raw_products:
                entry = process_price_match(
                    store,
                    prod.get("product", ""),
                    prod.get("price", 0),
                    prod.get("unit", ""),
                    ingredients,
                )
                if entry:
                    matched += 1
                    all_products.append(entry)

            print(f"[{store['name']}] {len(raw_products)} products, {matched} matched")

        except Exception as e:
            print(f"[{store['name']}] Error: {e}")
            try:
                send_scraper_error(store["name"], str(e))
            except Exception:
                pass

    return all_products


def collect_tier3_websites(ingredients: list[dict]) -> list[dict]:
    stores = [
        s for s in load_stores()
        if s.get("scraper") == "website_scraper"
        and s.get("type") == "website_catalog"
    ]
    all_products = []

    for store in stores:
        try:
            scraper = WebsiteScraper(store)
            raw_products = scraper.run(ingredients)
            if not raw_products:
                print(f"[{store['name']}] No products found")
                continue

            matched = 0
            for prod in raw_products:
                entry = process_price_match(
                    store,
                    prod.get("product", ""),
                    prod.get("price", 0),
                    prod.get("unit", ""),
                    ingredients,
                )
                if entry:
                    matched += 1
                    all_products.append(entry)

            print(f"[{store['name']}] {len(raw_products)} products, {matched} matched")

        except Exception as e:
            print(f"[{store['name']}] Error: {e}")
            try:
                send_scraper_error(store["name"], str(e))
            except Exception:
                pass

    return all_products


def collect_carrefour(ingredients: list[dict]) -> list[dict]:
    stores = [
        s for s in load_stores()
        if s.get("scraper") == "carrefour_scraper"
        and s.get("type") == "website_catalog"
    ]
    all_products = []

    for store in stores:
        try:
            scraper = CarrefourScraper(store)
            raw_products = scraper.run(ingredients)
            if not raw_products:
                print(f"[{store['name']}] No products found")
                continue

            matched = 0
            for prod in raw_products:
                entry = process_price_match(
                    store,
                    prod.get("product", ""),
                    prod.get("price", 0),
                    prod.get("unit", ""),
                    ingredients,
                )
                if entry:
                    matched += 1
                    all_products.append(entry)

            print(f"[{store['name']}] {len(raw_products)} products, {matched} matched")

        except Exception as e:
            print(f"[{store['name']}] Error: {e}")
            try:
                send_scraper_error(store["name"], str(e))
            except Exception:
                pass

    return all_products


def collect_aggregators_ssr() -> list[dict]:
    stores = [
        s for s in load_stores()
        if s.get("scraper") == "aggregator_scraper"
        and s.get("type") == "aggregator"
    ]
    all_flyers = []

    for store in stores:
        try:
            scraper = TiendeoScraper(store)
            flyers = scraper.run()
            if not flyers:
                print(f"[{store['name']}] No flyers found")
                continue

            saved = 0
            for flyer in flyers:
                try:
                    upsert_flyer(flyer)
                    saved += 1
                except Exception as e:
                    print(f"  Flyer save error: {e}")

            print(f"[{store['name']}] {len(flyers)} flyers found, {saved} saved")

        except Exception as e:
            print(f"[{store['name']}] Error: {e}")
            if store.get("experimental"):
                print("  (experimental, continuing)")
                continue
            try:
                send_scraper_error(store["name"], str(e))
            except Exception:
                pass

    return all_flyers


def collect_aggregators_js() -> list[dict]:
    stores = [
        s for s in load_stores()
        if s.get("scraper") == "playwright_scraper"
        and s.get("type") == "aggregator_js"
    ]
    all_flyers = []

    for store in stores:
        try:
            from scrapers.playwright_scraper import PlaywrightAggregatorScraper
            scraper = PlaywrightAggregatorScraper(store)
            flyers = scraper.run()
            if not flyers:
                print(f"[{store['name']}] No flyers found")
                continue

            saved = 0
            for flyer in flyers:
                try:
                    upsert_flyer(flyer)
                    saved += 1
                except Exception as e:
                    print(f"  Flyer save error: {e}")

            print(f"[{store['name']}] {len(flyers)} flyers found, {saved} saved")

        except Exception as e:
            print(f"[{store['name']}] Error: {e}")
            try:
                send_scraper_error(store["name"], str(e))
            except Exception:
                pass

    return all_flyers


def process_ocr_queue() -> int:
    from services.flyer_service import get_pending_flyers, mark_processed, mark_failed
    import httpx

    pending = get_pending_flyers(limit=10)
    if not pending:
        return 0

    processed = 0
    for flyer in pending:
        try:
            img_url = flyer["image_url"]
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

            mark_processed(flyer["id"], products_count=0)
            processed += 1

        except Exception as e:
            print(f"[OCR] Error processing flyer {flyer.get('id')}: {e}")
            try:
                mark_failed(flyer["id"])
            except Exception:
                pass

    return processed


def main():
    print("=" * 50)
    print("CustoDoce - Coleta de Preços")
    print(f"Início: {datetime.now().isoformat()}")
    print("=" * 50)

    ingredients = load_ingredients()
    print(f"\n📋 {len(ingredients)} ingredientes carregados")

    # Collect Tier 1: PDF flyers
    print("\n📄 Coletando Tier 1 (PDFs)...")
    tier1_products = collect_tier1_pdfs(ingredients)
    print(f"   → {len(tier1_products)} preços coletados")

    # Collect Tier 2a: VTEX e-commerce
    print("\n🛒 Coletando Tier 2a (VTEX)...")
    tier2_products = collect_tier2_vtex(ingredients)
    print(f"   → {len(tier2_products)} preços coletados")

    # Collect Tier 3: Website scrapers
    print("\n🌐 Coletando Tier 3 (Websites)...")
    tier3_products = collect_tier3_websites(ingredients)
    print(f"   → {len(tier3_products)} preços coletados")

    # Carrefour
    print("\n🛒 Coletando Carrefour...")
    carrefour_products = collect_carrefour(ingredients)
    print(f"   → {len(carrefour_products)} preços coletados")

    # Aggregators SSR (Tiendeo)
    print("\n📰 Coletando Agregadores SSR...")
    ssr_flyers = collect_aggregators_ssr()
    print(f"   → {len(ssr_flyers)} folhetos coletados")

    # Save local snapshot
    all_products = tier1_products + tier2_products + tier3_products + carrefour_products
    snapshot = {
        "collected_at": datetime.now().isoformat(),
        "total_prices": len(all_products),
        "ingredients_found": len(set(p["ingredient_id"] for p in all_products)),
    }
    snapshot_path = DATA_DIR / "prices_latest.json"
    with open(snapshot_path, "w") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    # Generate email report (if we have data)
    if all_products:
        try:
            report_html = generate_report_html(all_products, ingredients)
            send_daily_report(report_html=report_html)
            print("✅ Relatório enviado por email")
        except Exception as e:
            print(f"⚠️ Erro ao enviar email: {e}")

    print(f"\n✅ Coleta concluída: {datetime.now().isoformat()}")


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

        rows += f"""
        <tr>
            <td><b>{ing_name}</b></td>
            <td>{best['store_name']}</td>
            <td>R$ {best['raw_price']:.2f}</td>
            <td>R$ {price_kg:.2f}/kg</td>
            <td>{len(prices)}</td>
        </tr>"""

    today = date.today().isoformat()
    html = f"""
    <html><body>
    <h2>📊 CustoDoce - Relatório Diário</h2>
    <p>Data: {today} | Total de itens: {len(products)}</p>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse">
        <tr style="background:#f0f0f0">
            <th>Ingrediente</th><th>Melhor Preço</th><th>Valor</th><th>R$/kg</th><th>Fontes</th>
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
