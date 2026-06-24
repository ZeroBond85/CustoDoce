# mypy: ignore-errors
import asyncio
import logging
import re

from playwright.async_api import Page, Browser
from scrapers.playwright_pool import get_browser_pool

logger = logging.getLogger(__name__)

CITY_SLUGS = {
    "santos": "Santos",
    "sao-vicente": "São Vicente",
    "praia-grande": "Praia Grande",
    "mongagua": "Mongaguá",
    "itanhaem": "Itanhaém",
    "peruibe": "Peruíbe",
    "sao-paulo": "São Paulo",
}


class PlaywrightAggregatorScraper:
    def __init__(self, store_config: dict):
        self.store = store_config
        self.name = store_config["name"]
        self.base_url = store_config["base_url"].rstrip("/")
        self.regions = store_config.get("regions", [])
        self.sp_zones = store_config.get("sp_zones", [])

    def _build_city_urls(self) -> list[tuple[str, str]]:
        urls = []
        for slug in self.regions:
            city_name = CITY_SLUGS.get(slug, slug.replace("-", " ").title())
            if slug == "sao-paulo":
                for zone in self.sp_zones:
                    zone_slug = zone.lower().replace(" ", "-")
                    urls.append((f"{self.base_url}/{slug}/{zone_slug}", f"São Paulo - {zone}"))
            else:
                urls.append((f"{self.base_url}/{slug}", city_name))
        return urls

    async def _extract_flyers(self, page: Page, source: str) -> list[dict]:
        flyers = []
        cards = await page.query_selector_all('[class*="flyer"], [class*="brochure"], article, [class*="catalog-card"]')

        for card in cards:
            try:
                title = await card.inner_text()
                img = await card.query_selector("img")
                img_src = await img.get_attribute("src") if img else ""
                link = await card.query_selector("a")
                href = await link.get_attribute("href") if link else ""

                store_match = re.search(r"([A-Za-zÀ-ÿ\s]+)", title)
                date_match = re.search(r"(\d{2}/\d{2}/\d{4})", title)

                if not img_src:
                    continue

                flyer = {
                    "store_name": store_match.group(1).strip() if store_match else self.name,
                    "region": "",
                    "flyer_title": title.strip()[:200],
                    "image_url": img_src,
                    "image_hash": f"{source}_{hash(img_src)}",
                    "source": source,
                }

                if href:
                    flyer["flyer_url"] = href if href.startswith("http") else f"{self.base_url}{href}"

                if date_match:
                    flyer["flyer_date_end"] = date_match.group(1)

                flyers.append(flyer)

            except Exception as e:  # nosec B112
                logger.warning("Falha ao extrair flyer: %s", e)
                continue

        return flyers

    async def _scrape_city(self, browser: Browser, url: str, region: str, source: str) -> list[dict]:
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            flyers = await self._extract_flyers(page, source)
            for f in flyers:
                f["region"] = region
            return flyers
        except Exception as e:
            logger.error("[%s] Error scraping %s: %s", self.name, url, e)
            return []
        finally:
            await page.close()

    async def run_async(self) -> list[dict]:
        source = self.name.lower().replace(" ", "_")
        city_urls = self._build_city_urls()

        pool = await get_browser_pool()
        browser = pool.browser
        try:
            tasks = [self._scrape_city(browser, url, region, source) for url, region in city_urls]
            results = await asyncio.gather(*tasks)
        finally:
            pass  # Pool handles cleanup

        all_flyers = []
        for flyers in results:
            all_flyers.extend(flyers)
        return all_flyers

    def run(self) -> list[dict]:
        return asyncio.run(self.run_async())
