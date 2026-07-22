import asyncio
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from playwright.async_api import Browser, Page

from scrapers.playwright_pool import get_browser_pool
from services.logger import logger

CITY_CACHE_FILE = Path("data") / "discovered_cities.json"
CITY_CACHE_TTL_DAYS = 7

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


# Portal-specific configurations
PORTAL_CONFIG = {
    "kimbino": {
        "wait_selectors": [".brochure-thumb:not(.placeholder)", "[data-brochure-id]", ".brochure-grid .brochure-thumb"],
        "card_selector": ".brochure-thumb:not(.placeholder)",
        "store_name_patterns": [
            r'class="shop[^"]*"[^>]*>([^<]+)',
            r'class="shop-name"[^>]*>([^<]+)',
            r'data-store-name="([^"]+)"',
        ],
        "flyer_link_patterns": [r"/brochure/", r"/brochure-mw/", r"/oferta/", r"/encarte/"],
        "pagination": "auto-scroll",
        "wait_timeout": 30000,
    },
    "portafolhetos": {
        "wait_selectors": [".brochure-thumb:not(.placeholder)", ".shop-info", ".flyer-card"],
        "card_selector": ".brochure-thumb:not(.placeholder)",
        "store_name_patterns": [
            r'class="shop[^"]*"[^>]*>([^<]+)',
            r'class="shop-name"[^>]*>([^<]+)',
            r'data-store="([^"]+)"',
        ],
        "flyer_link_patterns": [r"/oferta/", r"/encarte/", r"/brochure/", r"/flyer/"],
        "city_url_pattern": "ofertas/{city}",
        "pagination": "auto-scroll",
        "wait_timeout": 30000,
    },
    "roldao": {
        "wait_selectors": [".brochure-thumb", ".flyer-card", "[data-flyer-id]"],
        "card_selector": ".brochure-thumb, .flyer-card, [data-flyer-id]",
        "store_name_patterns": [
            r'class="shop[^"]*"[^>]*>([^<]+)',
            r'data-store="([^"]+)"',
        ],
        "flyer_link_patterns": [r"/oferta/", r"/encarte/", r"/brochure/"],
        "pagination": "auto-scroll",
        "wait_timeout": 30000,
    },
    "tiendeo": {
        "wait_selectors": [".brochure-thumb", ".flyer-card", "[data-testid='flyer']"],
        "card_selector": "[data-testid='flyer_list_item'], [data-testid='flyer'], .brochure-thumb",
        "store_name_patterns": [
            r'data-testid="flyer_item_retailer_name"[^>]*>([^<]+)',
            r'class="retailer-name"[^>]*>([^<]+)',
        ],
        "flyer_link_patterns": [r"/brochure/", r"/flyer/"],
        "pagination": "auto-scroll",
        "wait_timeout": 30000,
    },
}


def get_portal_config(source: str) -> dict:
    """Get portal-specific config, fallback to defaults."""
    source_lower = source.lower().replace(" ", "_")
    return PORTAL_CONFIG.get(source_lower, {
        "wait_selectors": [".brochure-thumb", ".flyer-card", "[class*='flyer'], [class*='brochure']"],
        "card_selector": "[class*='flyer'], [class*='brochure'], article",
        "store_name_patterns": [r'class="shop[^"]*"[^>]*>([^<]+)', r'data-store="([^"]+)"'],
        "flyer_link_patterns": [r"/brochure/", r"/flyer/", r"/oferta/", r"/encarte/"],
        "pagination": "auto-scroll",
        "wait_timeout": 30000,
    })


class PlaywrightAggregatorScraper:
    def __init__(self, store_config: dict):
        self.store = store_config
        self.name = store_config["name"]
        self.base_url = store_config["base_url"].rstrip("/")
        self.regions = store_config.get("regions", [])
        self.sp_zones = store_config.get("sp_zones", [])
        self.portal_config = get_portal_config(self.name)
        self.logger = logger
        self._available_regions: set[str] | None = self._load_or_discover_cities()

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
                self.logger.info("[%s] City cache expired (>=%d days)", self.name, CITY_CACHE_TTL_DAYS)
                return None
            return set(entry["available_slugs"])
        except Exception as e:
            self.logger.debug("[%s] Error loading city cache: %s", self.name, e)
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
            self.logger.warning("[%s] Failed to save city cache: %s", self.name, e)

    def _discover_from_az_pages(self, target_slugs: set[str]) -> set[str]:
        """Discover cities from A-Z letter pages (works on Kimbino)."""
        letters = {slug[0] for slug in target_slugs}
        found: set[str] = set()

        for letter in sorted(letters):
            url = f"{self.base_url}/cidades/{letter}/"
            for attempt in range(2):
                try:
                    resp = httpx.get(url, timeout=15.0, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0"})
                    resp.raise_for_status()
                    html_text = resp.text
                except Exception as e:
                    self.logger.debug("[%s] A-Z page error %s (attempt %d/2): %s", self.name, url, attempt + 1, e)
                    time.sleep(1)
                    continue
                break
            else:
                continue

            for href_match in re.finditer(r'href="([^"]+)"', html_text):
                href = href_match.group(1)
                m = re.match(r"/cidade/([^/]+)/", href) or re.match(r"/([a-z][a-z0-9-]*[a-z])/?$", href)
                if m:
                    slug = m.group(1)
                    if slug in target_slugs:
                        found.add(slug)

            if found == target_slugs:
                break
        return found

    def _discover_portafolhetos_cities(self) -> set[str]:
        """Discover cities from Portafolhetos city search API."""
        found: set[str] = set()
        api_base = "https://www.portafolhetos.com.br/city/list/"
        letters = list("abcdefghijklmnopqrstuvwxyz")

        # 1. Query each letter a-z for general discovery
        for letter in letters:
            try:
                resp = httpx.get(
                    api_base,
                    params={"query": letter, "population": 5000},
                    timeout=10.0,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if resp.status_code == 200:
                    for item in resp.json():
                        slug = item.get("sef", "")
                        if slug:
                            found.add(slug)
            except Exception as e:
                self.logger.debug("[%s] API discovery error for letter %s: %s", self.name, letter, e)

        # 2. Verify each configured city by direct name query (use display name with accents)
        for slug in self.regions:
            city_query = CITY_SLUGS.get(slug, slug.replace("-", " ").title())
            if not city_query:
                continue
            try:
                resp = httpx.get(
                    api_base,
                    params={"query": city_query, "population": 5000},
                    timeout=10.0,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if resp.status_code == 200:
                    for item in resp.json():
                        api_slug = item.get("sef", "")
                        if api_slug and api_slug not in found:
                            found.add(api_slug)
            except Exception as e:
                self.logger.debug("[%s] API city verify error for %s: %s", self.name, slug, e)

        self.logger.info("[%s] API discovery found %d cities", self.name, len(found))
        return found

    def _discover_available_cities(self) -> set[str]:
        target_slugs = set(self.regions)
        is_portafolhetos = "portafolhetos" in self.name.lower()
        found = self._discover_portafolhetos_cities() if is_portafolhetos else self._discover_from_az_pages(target_slugs)

        if found:
            self.logger.info("[%s] Discovered %d/%d cities", self.name, len(found), len(target_slugs))
            missing = target_slugs - found
            if missing:
                self.logger.warning("[%s] Cities NOT found on %s: %s", self.name, self.name, ", ".join(sorted(missing)))
        else:
            self.logger.warning("[%s] City discovery returned no results — will use all configured cities", self.name)

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
            self.logger.warning("[%s] City discovery failed: %s — using all configured cities", self.name, e)
            return set(self.regions)

    def _build_city_urls(self) -> list[tuple[str, str]]:
        """Build city-specific URLs based on portal requirements."""
        active = [r for r in self.regions if r in (self._available_regions or set(self.regions))]
        if not active:
            active = self.regions

        urls = []

        # Special handling for Portafolhetos: city-specific offer pages
        if "portafolhetos" in self.name.lower():
            for slug in active:
                city_name = CITY_SLUGS.get(slug, slug.replace("-", " ").title())
                urls.append((f"{self.base_url}/ofertas/{slug}/", city_name))
            return urls

        # For Kimbino and others, use base URL + region slug
        if "kimbino" in self.name.lower():
            for slug in active:
                city_name = CITY_SLUGS.get(slug, slug.replace("-", " ").title())
                urls.append((f"{self.base_url}/{slug}", CITY_SLUGS.get(slug, slug.replace("-", " ").title())))
            return urls

        # Default: base URL + region
        for slug in active:
            city_name = CITY_SLUGS.get(slug, slug.replace("-", " ").title())
            if slug == "sao-paulo":
                for zone in self.sp_zones:
                    zone_slug = zone.lower().replace(" ", "-")
                    urls.append((f"{self.base_url}/{slug}/{zone_slug}", f"São Paulo - {zone}"))
            else:
                urls.append((f"{self.base_url}/{slug}", city_name))
        return urls

    async def _wait_for_real_content(self, page: Page, source: str) -> bool:
        """Wait for real flyer content to hydrate (skip skeleton placeholders)."""
        portal_config = get_portal_config(source)
        wait_timeout = portal_config["wait_timeout"]

        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < wait_timeout / 1000:
            # Check for real content (non-placeholder cards)
            for sel in portal_config["wait_selectors"]:
                try:
                    count = await self._count_elements(page, sel)
                    if count > 0 and not await self._is_placeholder(page, sel):
                        self.logger.info(f"[{self.name}] Real content found: {count} cards via '{sel}'")
                        return True
                except Exception as e:
                    self.logger.debug("[%s] Error checking selector: %s", self.name, e)

            # Check for known store names in page
            html_lower = (await self._get_page_html(page)).lower()
            known_stores = [
                "carrefour", "assai", "extra", "dia", "pao", "pão", "giga",
                "mambo", "makro", "mateus", "guanabara", "bom-preco", "pag-menos",
                "drogaria", "drogasil", "raia", "pague-menos", "rede-krill",
                "funchal", "santa-luzia", "casa-santa", "giga-atacadista",
            ]
            if any(store in html_lower for store in known_stores):
                self.logger.info(f"[{self.name}] Known store name found in page")
                return True

            await asyncio.sleep(2)

        self.logger.warning(f"[{self.name}] Timeout waiting for real content")
        return False

    async def _is_placeholder(self, page: Page, selector: str) -> bool:
        """Check if matched elements are skeleton placeholders."""
        try:
            elements = await page.query_selector_all(selector)
            for el in elements[:5]:  # Check first 5
                aria_hidden = await el.get_attribute("aria-hidden")
                cls = await el.get_attribute("class")
                if aria_hidden == "true" or (cls and "placeholder" in cls.lower()):
                    return True
        except Exception as e:
            self.logger.debug("[%s] Error checking placeholder: %s", self.name, e)
        return False

    async def _count_elements(self, page: Page, selector: str) -> int:
        try:
            return await page.locator(selector).count()
        except Exception:
            return 0

    async def _get_page_html(self, page: Page) -> str:
        return await page.content()

    async def _extract_flyers(self, page: Page, source: str) -> list[dict]:
        """Extract flyers from page using portal-specific logic."""
        portal_config = get_portal_config(source)

        flyers = []

        # Find all candidate cards
        cards = await page.query_selector_all(portal_config["card_selector"])
        self.logger.info(f"[{self.name}] Found {len(cards)} candidate cards with '{portal_config['card_selector']}'")

        # Fallback de resiliência: agregadores JS mudam a estrutura de classe
        # frequentemente. Se nenhum card casar, varremos TODOS os <a> da pagina
        # cujo href contenha um padrao de folheto — assim o scraper nao quebra
        # so porque a classe CSS do card mudou (ex.: Promotons).
        fallback_mode = False
        if not cards:
            self.logger.info(f"[{self.name}] No cards matched; falling back to all <a> links with flyer patterns")
            cards = await page.query_selector_all("a[href]")
            fallback_mode = True

        flyer_patterns = portal_config["flyer_link_patterns"]

        for card in cards:
            try:
                # Get full card HTML for robust parsing
                card_html = await card.inner_html()

                # Extract store name
                store_name = self.name
                for pattern in portal_config["store_name_patterns"]:
                    match = re.search(pattern, await card.inner_html(), re.I)
                    if match:
                        store_name = match.group(1).strip()
                        break

                # Extract flyer URL
                flyer_url = ""

                def _href_has_flyer_pattern(href: str) -> bool:
                    h = (href or "").lower()
                    return any(p.strip("/") in h for p in flyer_patterns)

                # Se o proprio card ja eh um <a> (fallback de pagina inteira),
                # pega o href direto antes de procurar dentro do HTML.
                try:
                    own_href = await card.get_attribute("href")
                except Exception:
                    own_href = None
                if own_href and _href_has_flyer_pattern(own_href):
                    flyer_url = own_href
                if not flyer_url:
                    card_html = await card.inner_html()
                    for pattern in flyer_patterns:
                        match = re.search(rf'href="([^"]*{pattern}[^"]*)"', card_html, re.I)
                        if match:
                            flyer_url = match.group(1)
                            break

                # Also try to get link from card's <a> tags
                if not flyer_url:
                    links = await card.query_selector_all("a")
                    for link in links:
                        href = await link.get_attribute("href")
                        if href and _href_has_flyer_pattern(href):
                            flyer_url = href
                            break

                # Get image
                img_src = ""
                img = await card.query_selector("img")
                if img:
                    img_src = await img.get_attribute("src") or await img.get_attribute("data-src") or ""

                # No fallback de pagina inteira, descarta links de navegacao que
                # nao casam com nenhum padrao de folheto e nao tem imagem (evita
                # poluir o OCR queue com menu/rodape). No modo card normal,
                # mantem o comportamento original.
                if fallback_mode and not flyer_url and not img_src:
                    continue

                # Get title/description
                title = ""
                try:
                    title = await card.inner_text()
                    title = re.sub(r"\s+", " ", title.strip())[:200]
                except Exception as e:
                    self.logger.debug("[%s] Error getting title: %s", self.name, e)

                # Extract date
                date_match = re.search(r"(\d{2}/\d{2}/\d{4})", card_html)

                # Filter out placeholders
                if "placeholder" in card_html.lower() or "skeleton" in card_html.lower():
                    continue

                if not img_src and not flyer_url:
                    if title and "placeholder" not in title.lower() and "skeleton" not in title.lower():
                        pass
                    else:
                        continue

                flyer = {
                    "store_name": store_name,
                    "region": "",
                    "flyer_title": title or "Folheto",
                    "image_url": img_src,
                    "image_hash": f"{source}_{hash(img_src or flyer_url or title)}",
                    "source": source,
                }

                if flyer_url:
                    flyer["flyer_url"] = flyer_url if flyer_url.startswith("http") else f"{self.base_url}{flyer_url}"

                if date_match:
                    flyer["flyer_date_end"] = date_match.group(1)

                flyers.append(flyer)

            except Exception as e:
                self.logger.warning(f"[{self.name}] Error extracting flyer: {e}")
                continue

        self.logger.info(f"[{self.name}] Extracted {len(flyers)} flyers")
        return flyers

    async def _scrape_city(self, browser: Browser, url: str, region: str, source: str) -> list[dict]:
        page = await browser.new_page()
        try:
            # Use domcontentloaded instead of networkidle (avoids SPA hang)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait for real content to hydrate (skip skeleton placeholders)
            await self._wait_for_real_content(page, source)

            # Auto-scroll for pagination if needed
            portal_config = get_portal_config(source)
            if portal_config.get("pagination") == "auto-scroll":
                await self._auto_scroll(page)

            flyers = await self._extract_flyers(page, source)
            for f in flyers:
                f["region"] = region
            return flyers

        except Exception as e:
            self.logger.error("[%s] Error scraping %s: %s", self.name, url, e)
            return []
        finally:
            await page.close()

    async def _auto_scroll(self, page: Page, max_scrolls: int = 5) -> None:
        """Scroll to trigger lazy-loading / pagination."""
        for _ in range(max_scrolls):
            before = await page.evaluate("document.body.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            after = await page.evaluate("document.body.scrollHeight")
            if after == before:
                break

    async def _enrich_portafolhetos_images(self, flyers: list[dict]) -> list[dict]:
        """Visit each flyer page via httpx to get full-res image from og:image meta."""
        import re as _re

        enriched = []
        for flyer in flyers:
            flyer_url = flyer.get("flyer_url", "")
            if not flyer_url or not flyer.get("image_url", ""):
                enriched.append(flyer)
                continue
            try:
                resp = httpx.get(
                    flyer_url,
                    timeout=15.0,
                    follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
                match = _re.search(
                    r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"',
                    resp.text,
                )
                if match:
                    full_url = match.group(1)
                    if full_url != flyer["image_url"]:
                        self.logger.debug(
                            "[%s] Upgraded image: %s -> %s",
                            self.name,
                            flyer["image_url"][:60],
                            full_url[:60],
                        )
                        flyer["image_url"] = full_url
            except Exception as e:
                self.logger.debug("[%s] Image enrich error for %s: %s", self.name, flyer_url, e)
            enriched.append(flyer)
        return enriched

    async def run_async(self) -> list[dict]:
        source = self.name.lower().replace(" ", "_")
        city_urls = self._build_city_urls()

        self.logger.info(f"[{self.name}] Scraping {len(city_urls)} cities/regions")

        pool = await get_browser_pool()
        browser = await pool.get_browser()
        try:
            tasks = [self._scrape_city(browser, url, region, source) for url, region in city_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            pass  # Pool handles cleanup

        all_flyers: list[dict] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error("[%s] City %s failed: %s", self.name, city_urls[i], result)
                continue
            all_flyers.extend(result)  # type: ignore[arg-type]

        # Portafolhetos: upgrade thumbnail URLs to full-res via og:image
        if "portafolhetos" in self.name.lower() and all_flyers:
            self.logger.info("[%s] Enriching %d flyers with full-res images...", self.name, len(all_flyers))
            all_flyers = await self._enrich_portafolhetos_images(all_flyers)

        self.logger.info(f"[{self.name}] Total flyers collected: {len(all_flyers)}")
        return all_flyers

    def run(self) -> list[dict]:
        return asyncio.run(self.run_async())


class PlaywrightTiendeoScraper:
    """Playwright-based fallback scraper for Tiendeo when HTTP requests fail/block."""

    def __init__(self, store_config: dict):
        self.store = store_config
        self.name = store_config["name"]
        self.base_url = store_config["base_url"].rstrip("/")
        self.regions = store_config.get("regions", [])
        self.sp_zones = store_config.get("sp_zones", [])
        self._available_regions: set[str] | None = self._load_cached_regions()

    def _load_cached_regions(self) -> set[str] | None:
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

    def _build_city_urls(self) -> list[tuple[str, str]]:
        active = [r for r in self.regions if r in (self._available_regions or set(self.regions))]
        if not active:
            active = self.regions
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

    async def _fetch_city(self, browser: Browser, url: str) -> str | None:
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            return await page.content()
        except Exception as e:
            logger.warning("[%s] Playwright error for %s: %s", self.name, url, e)
            return None
        finally:
            await page.close()

    async def _scrape_city(self, browser: Browser, url: str, region: str) -> list[dict]:
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            return await self._parse_flyers(page, region)
        except Exception as e:
            logger.warning("[%s] Playwright error for %s: %s", self.name, url, e)
            return []
        finally:
            await page.close()

    async def _parse_flyers(self, page: Page, source: str) -> list[dict]:
        flyers = []
        cards = await page.query_selector_all('a[href*="/Catalogos/"][href*="utm_medium"]')
        for card in cards:
            try:
                href = await card.get_attribute("href") or ""
                flyer_url = f"{self.base_url}{href}" if href.startswith("/") else href

                img_el = await card.query_selector("img")
                store_name = ""
                if img_el:
                    store_name = (await img_el.get_attribute("alt") or "").strip()
                if not store_name:
                    store_name = await card.inner_text() or ""
                    store_name = store_name.split("\n")[0].strip()
                if not store_name:
                    continue

                img_big = await card.query_selector('img[class*="object-contain"]:not([class*="blur"])')
                img_small = await card.query_selector("img")
                image_url = ""
                if img_big:
                    image_url = await img_big.get_attribute("src") or ""
                elif img_small:
                    src = (await img_small.get_attribute("src") or "")
                    if "blur" not in src.lower():
                        image_url = src
                if image_url and image_url.startswith("//"):
                    image_url = "https:" + image_url

                flyer_id = ""
                if "/Catalogos/" in href:
                    flyer_id = "catalog_" + href.split("/Catalogos/")[-1].split("?")[0]

                flyer_title = ""
                if img_el:
                    flyer_title = (await img_el.get_attribute("alt") or "").strip()

                flyers.append({
                    "store_name": store_name,
                    "region": source,
                    "flyer_title": flyer_title,
                    "flyer_url": flyer_url,
                    "image_url": image_url,
                    "image_hash": f"tiendeo_{flyer_id}",
                    "source": "tiendeo",
                })
            except Exception as e:
                logger.warning("[%s] Falha ao extrair flyer: %s", self.name, e)
        return flyers

    async def _run_async(self) -> list[dict]:
        from scrapers.playwright_pool import get_browser_pool
        city_urls = self._build_city_urls()
        pool = await get_browser_pool()
        browser = await pool.get_browser()
        all_flyers: list[dict] = []
        for url, region in city_urls:
            flyers = await self._scrape_city(browser, url, region)
            all_flyers.extend(flyers)
        return all_flyers

    def run(self) -> list[dict]:
        return asyncio.run(self._run_async())
