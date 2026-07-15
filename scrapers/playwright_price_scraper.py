import asyncio
import contextlib
import re
import time as _time

from selectolax.parser import HTMLParser

from parsers.unit_extractor import extract_unit
from scrapers.base_web_scraper import DEFAULT_SELECTORS, BaseWebScraper
from scrapers.playwright_pool import get_browser_pool
from services.logger import logger


class PlaywrightPriceScraper(BaseWebScraper):
    def __init__(self, store_config: dict):
        super().__init__(store_config)
        self.search_url = store_config.get("search_url") or f"{self.base_url}/busca?q={{query}}"
        # browse_urls: full category/department URLs. Some Lojas Integrada
        # (Tray) themes expose a broken /busca?q= search (returns no products)
        # while department pages render products correctly. When set, the
        # scraper browses these pages and collects ALL products; downstream
        # process_price_match filters by ingredient.
        self.browse_urls = list(store_config.get("browse_urls", []) or [])
        self.selectors = {**DEFAULT_SELECTORS, **store_config.get("selectors", {})}

    def run(self, ingredients: list[dict]) -> list[dict]:
        return asyncio.run(self._run_async(ingredients))

    async def _run_async(self, ingredients: list[dict]) -> list[dict]:
        all_products = []
        pool = await get_browser_pool()
        context = await pool.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        )
        try:
            if self.browse_urls:
                logger.info("[%s] browse mode: %d category URLs (asyncio.gather paralelo)", self.name, len(self.browse_urls))
                t0 = _time.time()
                tasks = [self._fetch_url(context, url, browse=True) for url in self.browse_urls]
                results = await asyncio.gather(*tasks)
                for url_idx, products in enumerate(results):
                    logger.info("[%s] %d products from %s (%.1fs)", self.name, len(products), self.browse_urls[url_idx], _time.time() - t0)
                    all_products.extend(products)
                logger.info("[%s] browse total: %d produtos %d urls em %.1fs", self.name, len(all_products), len(self.browse_urls), _time.time() - t0)
            else:
                for ing in ingredients:
                    products = await self._search_and_parse_async(context, ing)
                    all_products.extend(products)
        finally:
            await context.close()
        return all_products

    async def _search_and_parse_async(self, context, ing: dict) -> list[dict]:
        terms = list(ing.get("search_terms", []))
        canonical = ing.get("canonical_name", "")
        if canonical:
            terms.append(canonical)
        for alias in ing.get("aliases", []):
            terms.append(alias)

        for term in terms:
            if not term:
                continue
            try:
                products = await self._fetch_and_parse(context, term)
                if products:
                    return products
            except Exception as e:
                logger.debug("[%s] term '%s' failed: %s", self.name, term, e)
        return []

    async def _fetch_and_parse(self, context, query: str) -> list[dict]:
        from urllib.parse import quote

        url = self.search_url.format(query=quote(query))
        return await self._fetch_url(context, url, browse=False)

    async def _fetch_url(self, context, url: str, browse: bool = False) -> list[dict]:
        page = await context.new_page()
        try:
            # domcontentloaded resolves as soon as the SPA shell is parsed.
            # networkidle is unsafe on JS-heavy sites: the network often never
            # goes fully idle, causing every request to burn the full 30s timeout.
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Wait for product cards to actually render (graceful if absent).
            first_card_sel = self.selectors["product_card"][0]
            with contextlib.suppress(Exception):
                await page.wait_for_selector(first_card_sel, timeout=10000)
            if browse:
                # Some themes paginate via a "ver mais" button instead of
                # URL pagination. Click up to 3 times to expand the listing.
                for _ in range(3):
                    try:
                        clicked = await page.evaluate(
                            """() => {
                                const btns = Array.from(document.querySelectorAll('button'));
                                const b = btns.find(x => (x.textContent||'').trim().toLowerCase() === 'ver mais');
                                if (b) { b.scrollIntoView(); b.click(); return true; }
                                return false;
                            }"""
                        )
                    except Exception:
                        clicked = False
                    if not clicked:
                        break
                    await page.wait_for_timeout(3000)
            await page.wait_for_timeout(1500)
            html = await page.content()
        except Exception as e:
            logger.warning("[%s] Playwright error for '%s': %s", self.name, url, e)
            return []
        finally:
            await page.close()

        return self._extract_products(html)

    def _extract_products(self, html: str) -> list[dict]:
        tree = HTMLParser(html)
        cards = self._find_nodes(tree)
        products = []
        for card in cards:
            name = self._extract_name(card)
            if not name:
                continue
            price = self._extract_price(card)
            if price is None:
                continue
            unit = extract_unit(name)
            validity = self._extract_validity(card)
            products.append(
                {
                    "product": name.strip(),
                    "price": price,
                    "unit": unit,
                    "validity_raw": validity,
                    "brand": "",
                }
            )
        return products

    def _find_nodes(self, tree: HTMLParser) -> list:
        for selector in self.selectors["product_card"]:
            nodes = tree.css(selector)
            if nodes:
                return nodes
        return []

    def _extract_name(self, node) -> str | None:
        for selector in self.selectors["product_name"]:
            found = node.css(selector)
            if found:
                text = found[0].text().strip()
                if text:
                    return text
        text = node.text().strip()
        return text if text else None

    def _extract_price(self, node) -> float | None:
        for selector in self.selectors["product_price"]:
            found = node.css(selector)
            if found:
                text = found[0].text().strip()
                price = self._parse_price(text)
                if price is not None:
                    return price
        return None

    @staticmethod
    def _parse_price(text: str) -> float | None:
        m = re.search(r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)", text)
        if m:
            raw = m.group(1).replace(".", "").replace(",", ".")
            try:
                return float(raw)
            except ValueError:
                pass
        return None

    def _extract_validity(self, node) -> str:
        for selector in self.selectors.get("product_validity", []):
            found = node.css(selector)
            if found:
                text = found[0].text().strip()
                if text:
                    return text
        return ""

    # Implement abstract method from BaseWebScraper
    def parse_products(self, html: str) -> list[dict]:
        return self._extract_products(html)
