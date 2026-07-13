#!/usr/bin/env python3
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.collector import process_price_match
from services.config_db import get_active_ingredients
from services.supabase_client import get_service_client, get_supabase
from services.telegram_service import send_telegram_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    client = get_supabase()
    service_client = get_service_client()

    # 1. Get pending requests
    res = client.table("scrape_requests").select("*").eq("status", "pending").execute()
    requests = res.data or []

    if not requests:
        logger.info("No pending scrape requests.")
        return

    ingredients = get_active_ingredients()

    for req in requests:
        req_id = req["id"]
        store_id = req["store_id"]
        user_id = req["user_id"]

        # Get store details
        store_res = client.table("stores").select("*").eq("id", store_id).maybe_single().execute()
        if not store_res.data:
            logger.error(f"Store {store_id} not found. Marking as failed.")
            service_client.table("scrape_requests").update({"status": "failed"}).eq("id", req_id).execute()
            continue

        store = store_res.data
        logger.info(f"Processing on-demand scrape for {store['name']} (User: {user_id})")

        try:
            # Since we don't have a full scraper orchestration here,
            # we'll try to use the corresponding scraper class based on the store's scraper field
            from services.collector import (
                CarrefourScraper,
                ExtraFlyerScraper,
                FacebookFlyerScraper,
                FlyerScraper,
                MaxApiScraper,
                PaoFlyerScraper,
                PlaywrightPriceScraper,
                RoldaoApiScraper,
                TendaApiScraper,
                VtexScraper,
                WebsiteScraper,
            )

            SCRAPER_MAP = {
                "flyer_scraper": FlyerScraper,
                "extra_flyer_scraper": ExtraFlyerScraper,
                "pao_flyer_scraper": PaoFlyerScraper,
                "vtex_scraper": VtexScraper,
                "website_scraper": WebsiteScraper,
                "carrefour_scraper": CarrefourScraper,
                "tenda_api_scraper": TendaApiScraper,
                "roldao_api_scraper": RoldaoApiScraper,
                "max_api_scraper": MaxApiScraper,
                "playwright_price_scraper": PlaywrightPriceScraper,
                "facebook_flyer_scraper": FacebookFlyerScraper,
            }

            scraper_name = store.get("scraper")
            scraper_cls = SCRAPER_MAP.get(scraper_name)

            if not scraper_cls:
                raise ValueError(f"No scraper class found for {scraper_name}")

            with scraper_cls(store) as scraper:
                raw_products = scraper.run(ingredients)

                matched_count = 0
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
                        matched_count += 1

                # Mark as completed and notify user
                service_client.table("scrape_requests").update(
                    {"status": "completed", "processed_at": datetime.now(UTC).isoformat()}
                ).eq("id", req_id).execute()

                send_telegram_message(
                    user_id,
                    f"✅ <b>Coleta Concluída!</b>\n\nLoja: {store['name']}\nProdutos encontrados: {len(raw_products)}\nMatches: {matched_count}",
                )
                logger.info(f"Successfully scraped {store['name']} for user {user_id}")

        except Exception as e:
            logger.error(f"Failed to scrape {store['name']}: {e}")
            service_client.table("scrape_requests").update({"status": "failed"}).eq("id", req_id).execute()
            send_telegram_message(user_id, f"❌ <b>Erro na Coleta</b>\n\nLoja: {store['name']}\nErro: {str(e)}")


if __name__ == "__main__":
    main()
