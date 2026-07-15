import asyncio
import re

from playwright.async_api import Browser, Page

from scrapers.playwright_pool import get_browser_pool
from services.logger import logger

CITY_SLUGS = {
    "santos": "Santos",
    "sao-vicente": "São Vicente",
    "praia-grande": "Praia Grande",
    "mongagua": "Mongaguá",
    "itanhaem": "Itanhaém",
    "peruibe": "Peruíbe",
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
    "promotons": {
        "wait_selectors": [".brochure-thumb", ".flyer-item", ".catalog-card"],
        "card_selector": "[class*='brochure'], [class*='flyer'], [class*='catalog']",
        "store_name_patterns": [
            r'class="shop[^"]*"[^>]*>([^<]+)',
            r'class="store-name"[^>]*>([^<]+)',
        ],
        "flyer_link_patterns": [r"/brochure/", r"/flyer/", r"/encarte/"],
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

    def _build_city_urls(self) -> list[tuple[str, str]]:
        """Build city-specific URLs based on portal requirements."""
        urls = []

        # Special handling for Portafolhetos: city-specific offer pages
        if "portafolhetos" in self.name.lower():
            for slug in self.regions:
                city_name = CITY_SLUGS.get(slug, slug.replace("-", " ").title())
                urls.append((f"{self.base_url}/ofertas/{slug}/", city_name))
            return urls

        # For Kimbino and others, use base URL + region slug
        if "kimbino" in self.name.lower():
            for slug in self.regions:
                city_name = CITY_SLUGS.get(slug, slug.replace("-", " ").title())
                urls.append((f"{self.base_url}/{slug}", CITY_SLUGS.get(slug, slug.replace("-", " ").title())))
            return urls

        # Default: base URL + region
        for slug in self.regions:
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
            html_lower = await self._get_page_html(page).lower()
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
                card_html = await card.inner_html()
                for pattern in portal_config["flyer_link_patterns"]:
                    match = re.search(rf'href="([^"]*{pattern}[^"]*)"', card_html, re.I)
                    if match:
                        flyer_url = match.group(1)
                        break

                # Also try to get link from card's <a> tags
                if not flyer_url:
                    links = await card.query_selector_all("a")
                    for link in links:
                        href = await link.get_attribute("href")
                        if href and any(p in href.lower() for p in ["brochure", "encarte", "oferta", "catalogo", "flyer", "oferta"]):
                            flyer_url = href
                            break

                # Get image
                img_src = ""
                img = await card.query_selector("img")
                if img:
                    img_src = await img.get_attribute("src") or await img.get_attribute("data-src") or ""

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

        all_flyers = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error("[%s] City %s failed: %s", self.name, city_urls[i], result)
                continue
            all_flyers.extend(result)

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

    async def _parse_flyers(self, page: Page, source: str) -> list[dict]:
        cards = await page.query_selector_all(
            '[data-testid="flyer_list_item"], .js-flyer, li[data-type="flyer"]'
        )

        for card in cards:
            try:
                store_name_el = await card.query_selector('[data-testid="flyer_item_retailer_name"]')
                title_el = await card.query_selector('[data-testid="flyer_item_title"]')
                await card.get_attribute("data-id")  # consume but don't store

                if not store_name_el or not title_el:
                    continue

                # Placeholder for flyer extraction - would be implemented here
                _ = {
                    "store_name": (await store_name_el.inner_text()).strip(),
                    "flyer_title": (await title_el.inner_text()).strip(),
                    "image_url": "",
                    "source": "tiendeo",
                }
                # ... rest of extraction logic
            except Exception as e:
                logger.warning("Falha ao extrair flyer: %s", e)
        return []

    def run(self) -> list[dict]:
        return asyncio.run(self._run_async())


# Backward compatibility - TiendeoScraper uses aggregator_scraper.py
# This class is for Kimbino, Portafolhetos, Roldão, Promotons (JS portals)
