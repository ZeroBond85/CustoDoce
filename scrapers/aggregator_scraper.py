import asyncio
import logging
import re
from datetime import datetime

import httpx
from selectolax.parser import HTMLParser

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


class TiendeoScraper:
    def __init__(self, store_config: dict):
        self.store = store_config
        self.name = store_config["name"]
        self.base_url = store_config["base_url"].rstrip("/")
        self.regions = store_config.get("regions", [])
        self.sp_zones = store_config.get("sp_zones", [])
        self.session = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
            },
        )

    def _build_city_urls(self) -> list[tuple[str, str]]:
        urls = []
        for slug in self.regions:
            city_name = CITY_SLUGS.get(slug, slug.replace("-", " ").title())
            if slug == "sao-paulo":
                urls.append((f"{self.base_url}/sao-paulo", "São Paulo"))
                for zone in self.sp_zones:
                    zone_slug = zone.lower().replace(" ", "-")
                    urls.append((f"{self.base_url}/sao-paulo/{zone_slug}", f"São Paulo - {zone}"))
            else:
                urls.append((f"{self.base_url}/{slug}", city_name))
        return urls

    def fetch_city(self, url: str) -> str | None:
        try:
            resp = self.session.get(url)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.error("Error fetching %s: %s", url, e)
            return None

    def parse_flyers(self, html: str, region: str) -> list[dict]:
        tree = HTMLParser(html)
        flyers = []

        not_found = tree.css_first('.error-page, [class*="error"], h1')
        if not_found and "não encontramos" in not_found.text(strip=True).lower():
            logger.warning("Skipping %s: page not found", region)
            return flyers

        items = tree.css('[data-testid="flyer_list_item"], .js-flyer, li[data-type="flyer"]')
        for item in items:
            try:
                store_name = item.css_first('[data-testid="flyer_item_retailer_name"]')
                title_el = item.css_first('[data-testid="flyer_item_title"]')
                date_el = item.css_first('[data-testid="flyer_item_expiration"]')
                img_small = item.css_first('img[data-testid="blurred-background"]')
                img_big = item.css_first('img[class*="object-contain"]')
                flyer_id = item.attributes.get("data-id", "")

                if not store_name or not title_el:
                    continue

                flyer = {
                    "store_name": store_name.text().strip(),
                    "region": region,
                    "flyer_title": title_el.text().strip(),
                    "image_url": "",
                    "image_hash": f"tiendeo_{flyer_id}",
                    "source": "tiendeo",
                }

                if img_big:
                    flyer["image_url"] = img_big.attributes.get("src", "")
                elif img_small:
                    flyer["image_url"] = img_small.attributes.get("src", "")

                date_text = date_el.text().strip() if date_el else ""
                flyer["flyer_date_end"] = self._parse_date(date_text)

                if flyer["image_url"]:
                    flyers.append(flyer)

            except Exception as e:
                logger.error("Error parsing flyer: %s", e)
                continue

        return flyers

    def _parse_date(self, text: str) -> str | None:
        m = re.search(r"(\d{2})/(\d{2})", text)
        if m:
            raw_day, raw_month = int(m.group(1)), int(m.group(2))
            resolved_year = self._resolve_year(raw_month)
            return f"{resolved_year}-{raw_month:0>2}-{raw_day:0>2}"
        return None

    @staticmethod
    def _resolve_year(month: int) -> int:
        today = datetime.now()
        return today.year + 1 if month < today.month else today.year

    async def _fetch_city_async(self, client: httpx.AsyncClient, url: str) -> str | None:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.error("Error fetching %s: %s", url, e)
            return None

    async def run_async(self) -> list[dict]:
        city_urls = self._build_city_urls()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        }

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
            tasks = [self._fetch_city_async(client, url) for url, _ in city_urls]
            results = await asyncio.gather(*tasks)

        all_flyers = []
        for (url, region), html in zip(city_urls, results):
            if not html:
                continue
            flyers = self.parse_flyers(html, region)
            all_flyers.extend(flyers)

        return all_flyers

    def run(self) -> list[dict]:
        return asyncio.run(self.run_async())
