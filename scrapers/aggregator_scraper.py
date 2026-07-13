import asyncio
import random
import re
import time
from datetime import UTC, datetime

import httpx
from selectolax.parser import HTMLParser

from services.logger import logger

FOOD_KEYWORDS = {
    "supermercado",
    "mercado",
    "mercad",
    "atacad",
    "hiper",
    "padaria",
    "pao",
    "confeitaria",
    "confeiteiro",
    "doce",
    "doces",
    "empório",
    "emporio",
    "distribuidora",
    "distribuidor",
    "farinha",
    "frios",
    "açougue",
    "acougue",
    "hortifruti",
    "bebidas",
    "acucar",
    "alimentos",
    "guloseimas",
    "festas",
    "embalagens",
    "descartaveis",
    "descartáveis",
}
NON_FOOD_KEYWORDS = {
    "boticário",
    "boticario",
    "magazine",
    "casas bahia",
    "renner",
    "riachuelo",
    "marisa",
    "c&a",
    "cea",
    "drogaria",
    "farmacia",
    "farmácia",
    "drogasil",
    "drogão",
    "drogao",
    "polishop",
    "fast shop",
    "shop",
    "lojas",
    "melissa",
    "electrolux",
    "lg",
    "samsung",
    "sony",
    "apple",
    "posto",
    "gasolina",
    "combustivel",
    "pet",
    "petshop",
    "animal",
    "papelaria",
    "livraria",
    "academia",
    "ginastica",
    "ótica",
    "otica",
    "oculos",
    "seguros",
    "banco",
    "financiamento",
    "imobiliária",
    "imobiliaria",
    "imovel",
    "automoveis",
    "carro",
    "moto",
    "bicicleta",
    "cama",
    "mesa",
    "banho",
    "cama mesa banho",
    "material de construcao",
    "construcao",
    "construção",
    "presentes",
    "souvenir",
    "brinquedos",
    "jogos",
    "perfumaria",
    "cosmeticos",
    "cosméticos",
    "lavanderia",
    "limpeza",
}


def _is_food_store(store_name: str) -> bool:
    name_lower = store_name.lower().strip()
    if any(kw in name_lower for kw in NON_FOOD_KEYWORDS):
        return False
    if any(kw in name_lower for kw in FOOD_KEYWORDS):
        return True
    return True


def _fix_image_url(url: str) -> str:
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    if "example.com" in url or "placeholder" in url:
        return ""
    return url


CITY_SLUGS = {
    "santos": "Santos",
    "sao-vicente": "São Vicente",
    "praia-grande": "Praia Grande",
    "mongagua": "Mongaguá",
    "itanhaem": "Itanhaém",
    "peruibe": "Peruíbe",
    "sao-paulo": "São Paulo",
}

# User-Agent pool for rotation (helps avoid IP-based blocking)
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

DEFAULT_UA = UA_POOL[0]


class TiendeoScraper:
    def __init__(self, store_config: dict):
        self.store = store_config
        self.name = store_config["name"]
        self.base_url = store_config["base_url"].rstrip("/")
        self.regions = store_config.get("regions", [])
        self.sp_zones = store_config.get("sp_zones", [])
        self.ua_pool = UA_POOL
        self.session = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": DEFAULT_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "max-age=0",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
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

    def _rotate_ua(self) -> str:
        return random.choice(self.ua_pool)  # nosec B311

    def _retry_config(self) -> tuple[int, float, float]:
        """Return (max_retries, base_delay, max_delay)"""
        return 3, 2.0, 15.0

    def fetch_city(self, url: str) -> str | None:
        """Fetch with retry, UA rotation, and exponential backoff."""
        max_retries, base_delay, max_delay = self._retry_config()

        for attempt in range(max_retries + 1):
            ua = self._rotate_ua()
            self.session.headers.update({"User-Agent": ua})

            try:
                resp = self.session.get(url, timeout=30.0)
                resp.raise_for_status()
                html = resp.text

                # Verify we got real content (not blocked/empty)
                if len(html) < 10000 or "data-testid=\"flyer_list_item\"" not in html:
                    logger.warning("[%s] Suspicious response for %s (len=%d, flyers=%d) - attempt %d/%d",
                                   self.name, url, len(html), html.count("data-testid=\"flyer_list_item\""), attempt + 1, max_retries + 1)
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)  # nosec B311
                        logger.info("[%s] Retrying in %.1fs...", self.name, delay)
                        time.sleep(delay)
                        continue

                return html

            except httpx.HTTPStatusError as e:
                logger.warning("[%s] HTTP %d for %s - attempt %d/%d", self.name, e.response.status_code, url, attempt + 1, max_retries + 1)
            except Exception as e:
                logger.warning("[%s] Error fetching %s: %s - attempt %d/%d", self.name, url, e, attempt + 1, max_retries + 1)

            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)  # nosec B311
                logger.info("[%s] Retrying in %.1fs...", self.name, delay)
                time.sleep(delay)

        logger.error("[%s] All retries exhausted for %s", self.name, url)
        return None

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

                store_name_text = store_name.text().strip()
                if not _is_food_store(store_name_text):
                    logger.debug("Skipping non-food store: %s", store_name_text)
                    continue

                flyer = {
                    "store_name": store_name_text,
                    "region": region,
                    "flyer_title": title_el.text().strip(),
                    "image_url": "",
                    "image_hash": f"tiendeo_{flyer_id}",
                    "source": "tiendeo",
                }

                if img_big:
                    flyer["image_url"] = _fix_image_url(img_big.attributes.get("src", ""))
                elif img_small:
                    flyer["image_url"] = _fix_image_url(img_small.attributes.get("src", ""))

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
        today = datetime.now(UTC)
        return today.year + 1 if month < today.month else today.year

    async def _fetch_city_async(self, client: httpx.AsyncClient, url: str) -> str | None:
        for attempt in range(3):
            try:
                resp = await client.get(url, timeout=30.0)
                resp.raise_for_status()
                html = resp.text
                if len(html) < 10000 or "data-testid=\"flyer_list_item\"" not in html:
                    logger.warning("[%s] Suspicious async response for %s (len=%d)", self.name, url, len(html))
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                return html
            except Exception as e:
                logger.warning("[%s] Async fetch error %s: %s", self.name, url, e)
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
        return None

    async def run_async(self) -> list[dict]:
        city_urls = self._build_city_urls()
        headers = {
            "User-Agent": random.choice(UA_POOL),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
            tasks = [self._fetch_city_async(client, url) for url, _ in city_urls]
            results = await asyncio.gather(*tasks)

        all_flyers = []
        for (_url, region), html in zip(city_urls, results, strict=False):
            if not html:
                continue
            flyers = self.parse_flyers(html, region)
            all_flyers.extend(flyers)

        return all_flyers

    def run(self) -> list[dict]:
        return asyncio.run(self.run_async())


# Fallback Playwright-based scraper for when HTTP fails (e.g., IP blocking)
class TiendeoPlaywrightScraper:
    """Fallback scraper using Playwright when HTTP requests fail/block."""

    def __init__(self, store_config: dict):
        self.store = store_config
        self.name = store_config["name"]
        self.base_url = store_config["base_url"].rstrip("/")
        self.regions = store_config.get("regions", [])
        self.sp_zones = store_config.get("sp_zones", [])
        self.CITY_SLUGS = CITY_SLUGS

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

    def _build_playwright_scraper(self) -> PlaywrightTiendeoScraper:
        """Lazy import to avoid Playwright dependency in environments without it."""
        from scrapers.playwright_scraper import PlaywrightTiendeoScraper
        config = self.store.copy()
        config["scraper_type"] = "tiendeo"
        return PlaywrightTiendeoScraper(config)

    def run(self) -> list[dict]:
        """Run with retry logic and UA rotation for CI resilience."""
        http_scraper = TiendeoScraper(self.store)
        flyers = http_scraper.run()

        if flyers:
            logger.info("[%s] HTTP scraper succeeded: %d flyers", self.name, len(flyers))
            return flyers

        logger.warning("[%s] HTTP returned 0 flyers after retries; no Playwright fallback available", self.name)
        return []
