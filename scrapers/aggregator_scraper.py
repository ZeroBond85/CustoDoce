from __future__ import annotations

import asyncio
import json
import random
import re
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from selectolax.parser import HTMLParser

from services.logger import logger

if TYPE_CHECKING:
    from scrapers.playwright_scraper import PlaywrightTiendeoScraper

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
    "guaruja": "Guarujá",
    "sao-paulo": "São Paulo",
}

REVERSE_CITY_SLUGS = {v.lower().replace(" ", ""): k for k, v in CITY_SLUGS.items()}

CITY_CACHE_FILE = Path("data") / "discovered_cities.json"
CITY_CACHE_TTL_DAYS = 7


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
        # store_slug permite apontar para a página DEDICADA da loja no Tiendeo
        # (ex.: /Encartes-Catalogos/spani-atacadista), em vez de varrer todas as
        # cidades. Usado quando uma loja tem cobertura própria e estável.
        self.store_slug = store_config.get("store_slug")
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
        self._available_regions: set[str] | None = self._load_or_discover_cities()

    def _build_city_urls(self) -> list[tuple[str, str]]:
        # Filtra regiões para apenas as descobertas como disponíveis no site
        active = [r for r in self.regions if r in (self._available_regions or set(self.regions))]
        if not active:
            active = self.regions

        # Loja com página dedicada no Tiendeo: usa store_slug em vez de varrer cidades.
        if self.store_slug:
            base = f"{self.base_url}/Encartes-Catalogos/{self.store_slug}"
            if active:
                urls = [(f"{base}/{slug}", CITY_SLUGS.get(slug, slug.replace("-", " ").title())) for slug in active]
                if urls:
                    return urls
            return [(base, self.name)]
        urls = []
        for slug in active:
            city_name = CITY_SLUGS.get(slug, slug.replace("-", " ").title())
            if slug == "sao-paulo":
                urls.append((f"{self.base_url}/sao-paulo", "São Paulo"))
                for zone in self.sp_zones:
                    zone_slug = zone.lower().replace(" ", "-")
                    urls.append((f"{self.base_url}/sao-paulo/{zone_slug}", f"São Paulo - {zone}"))
            else:
                urls.append((f"{self.base_url}/{slug}", city_name))
        return urls

    def _load_city_cache(self) -> set[str] | None:
        if not CITY_CACHE_FILE.exists():
            return None
        try:
            data = json.loads(CITY_CACHE_FILE.read_text(encoding="utf-8"))
            entry = data.get(self.name)
            if entry is None:
                return None
            discovered_at = datetime.fromisoformat(entry["discovered_at"])
            if (datetime.now(UTC) - discovered_at).days >= CITY_CACHE_TTL_DAYS:
                logger.info("[%s] City cache expired (>=%d days)", self.name, CITY_CACHE_TTL_DAYS)
                return None
            return set(entry["available_slugs"])
        except Exception as e:
            logger.debug("[%s] Error loading city cache: %s", self.name, e)
            return None

    def _save_city_cache(self, slugs: list[str]) -> None:
        try:
            CITY_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if CITY_CACHE_FILE.exists():
                data = json.loads(CITY_CACHE_FILE.read_text(encoding="utf-8"))
            data[self.name] = {
                "available_slugs": slugs,
                "discovered_at": datetime.now(UTC).isoformat(),
            }
            CITY_CACHE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning("[%s] Failed to save city cache: %s", self.name, e)

    def _fetch_page_raw(self, url: str) -> str | None:
        """Fetch a page with retry — no /Catalogos/ check (for city listing pages)."""
        for attempt in range(3):
            ua = self._rotate_ua()
            self.session.headers.update({"User-Agent": ua})
            try:
                resp = self.session.get(url, timeout=30.0)
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                logger.debug("[%s] Fetch error %s (attempt %d/3): %s", self.name, url, attempt + 1, e)
                if attempt < 2:
                    time.sleep(2 ** attempt)
        return None

    def _discover_available_cities(self) -> set[str]:
        target_slugs = set(self.regions)
        found: set[str] = set()

        for page_num in range(1, 21):
            page_url = f"{self.base_url}/Cidades?page={page_num}"
            html = self._fetch_page_raw(page_url)
            if not html:
                break

            tree = HTMLParser(html)
            for link in tree.css("a[href]"):
                href = (link.attributes.get("href") or "").strip()
                # City URLs on Tiendeo are single-segment: /santos, /sao-paulo
                if href.startswith("/") and href.count("/") == 1:
                    slug = href.strip("/")
                    if slug in target_slugs:
                        found.add(slug)

            if found == target_slugs:
                break

            # Check if next page exists (look for pagination link to page_num+1)
            next_str = f"page={page_num + 1}"
            if not any(next_str in (a.attributes.get("href") or "") for a in tree.css("a[href]")):
                break

        if found:
            logger.info("[%s] Discovered %d/%d cities on Tiendeo", self.name, len(found), len(target_slugs))
            missing = target_slugs - found
            if missing:
                logger.warning("[%s] Cities NOT found on Tiendeo: %s", self.name, ", ".join(sorted(missing)))
        else:
            logger.warning("[%s] City discovery returned no results — will use all configured cities", self.name)

        return found or set(self.regions)

    def _load_or_discover_cities(self) -> set[str] | None:
        cached = self._load_city_cache()
        if cached is not None:
            return cached
        try:
            discovered = self._discover_available_cities()
            if discovered:
                self._save_city_cache(list(discovered))
            return discovered
        except Exception as e:
            logger.warning("[%s] City discovery failed: %s — using all configured cities", self.name, e)
            return set(self.regions)

    def _rotate_ua(self) -> str:
        return random.choice(self.ua_pool)  # noqa: S311

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
                catalogos_count = html.count("/Catalogos/")
                if len(html) < 10000 or catalogos_count == 0:
                    logger.warning("[%s] Suspicious response for %s (len=%d, catalogos=%d) - attempt %d/%d",
                                   self.name, url, len(html), catalogos_count, attempt + 1, max_retries + 1)
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)  # noqa: S311
                        logger.info("[%s] Retrying in %.1fs...", self.name, delay)
                        time.sleep(delay)
                        continue

                return html

            except httpx.HTTPStatusError as e:
                logger.warning("[%s] HTTP %d for %s - attempt %d/%d", self.name, e.response.status_code, url, attempt + 1, max_retries + 1)
            except Exception as e:
                logger.error("[%s] Error fetching %s: %s - attempt %d/%d", self.name, url, e, attempt + 1, max_retries + 1)

            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)  # noqa: S311
                logger.info("[%s] Retrying in %.1fs...", self.name, delay)
                time.sleep(delay)

        logger.error("[%s] All retries exhausted for %s", self.name, url)
        return None

    def parse_flyers(self, html: str, region: str) -> list[dict]:
        tree = HTMLParser(html)
        seen: set[str] = set()
        flyers: list[dict] = []

        not_found = tree.css_first('.error-page, [class*="error"], h1')
        if not_found and "não encontramos" in not_found.text(strip=True).lower():
            logger.warning("Skipping %s: page not found", region)
            return flyers

        items = tree.css('[data-testid="flyer_list_item"], .js-flyer, li[data-type="flyer"]')
        for item in items:
            try:
                store_el = item.css_first('[data-testid="flyer_item_retailer_name"]')
                title_el = item.css_first('[data-testid="flyer_item_title"]')
                date_el = item.css_first('[data-testid="flyer_item_expiration"]')
                link_el = item.css_first('a[data-testid="flyer_item_link"]')

                if not store_el or not title_el:
                    continue

                store_name_text = store_el.text(strip=True)
                if not _is_food_store(store_name_text):
                    logger.debug("Skipping non-food store: %s", store_name_text)
                    continue

                href = (link_el.attributes.get("href") or "") if link_el else ""
                flyer_url = f"{self.base_url}{href}" if href.startswith("/") else href

                flyer_id = ""
                if "/Catalogos/" in href:
                    flyer_id = "catalog_" + href.split("/Catalogos/")[-1].split("?")[0]

                image_hash = f"tiendeo_{flyer_id}"
                if image_hash in seen:
                    continue
                seen.add(image_hash)

                flyer_title = title_el.text(strip=True)

                img_big = item.css_first('img[class*="object-contain"]')
                img_small = item.css_first('[data-testid="blurred-background"]')
                image_url = ""
                if img_big:
                    src = img_big.attributes.get("src") or ""
                    image_url = _fix_image_url(src)
                elif img_small:
                    src = img_small.attributes.get("src") or ""
                    image_url = _fix_image_url(src)

                date_text = date_el.text(strip=True) if date_el else ""

                flyers.append({
                    "store_name": store_name_text,
                    "region": region,
                    "flyer_title": flyer_title,
                    "flyer_url": flyer_url,
                    "image_url": image_url,
                    "image_hash": image_hash,
                    "flyer_date_end": self._parse_date(date_text),
                    "source": "tiendeo",
                })

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
                if len(html) < 10000 or "/Catalogos/" not in html:
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
            "User-Agent": random.choice(UA_POOL),  # noqa: S311
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
        flyers = asyncio.run(self.run_async())
        if flyers:
            with suppress(Exception):
                from services.scraper_health import record_success
                record_success(self.name, items_found=len(flyers), flyer_count=len(flyers), attempted_by="aggregator_scraper")
        return flyers


# Fallback Playwright-based scraper for when HTTP requests fail/block.
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
        """SSR scraper primary, Playwright fallback if HTTP fails or returns 0."""
        http_scraper = TiendeoScraper(self.store)
        flyers = http_scraper.run()

        if flyers:
            logger.info("[%s] HTTP scraper succeeded: %d flyers", self.name, len(flyers))
            return flyers

        logger.warning("[%s] HTTP returned 0 flyers — trying Playwright fallback", self.name)
        try:
            pw_scraper = self._build_playwright_scraper()
            flyers = pw_scraper.run()
            if flyers:
                logger.info("[%s] Playwright fallback succeeded: %d flyers", self.name, len(flyers))
            return flyers
        except Exception as e:
            logger.error("[%s] Playwright fallback failed: %s", self.name, e)
            return []

