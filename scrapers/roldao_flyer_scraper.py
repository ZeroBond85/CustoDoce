"""Roldão Atacadista flyer scraper for https://roldao.com.br/ofertas-do-roldao/.

Uses Playwright to render JavaScript-rendered flyer page.
"""

import asyncio
import logging
import re

from scrapers.playwright_pool import get_browser_pool

logger = logging.getLogger(__name__)

PRICE_RE = re.compile(r"(?:R\$\s*)?([1-9]\d{0,2}(?:\.\d{3})*\s*,\d{2})\b")

class RoldaoFlyerScraper:
    """Scraper para folhetos do Roldão em https://roldao.com.br/ofertas-do-roldao/.

    Usa Playwright para renderizar página JavaScript.
    """

    BASE_URL = "https://roldao.com.br/ofertas-do-roldao/"

    def __init__(self, store_config: dict):
        self.store = store_config
        self.name = store_config.get("name", "Roldão Atacadista")
        self.base_url = store_config.get("base_url", "https://roldao.com.br").rstrip("/")
        self.selectors = store_config.get("selectors", {})

    async def _extract_products(self, page) -> list[dict]:
        """Extrai produtos da página de ofertas."""
        products = []

        # Wait for content to load
        await page.wait_for_timeout(3000)

        # Try to find product cards
        cards = await page.query_selector_all('[class*="product"], [class*="offer"], [class*="item"], article, [class*="card"]')

        for card in cards:
            try:
                # Try to extract name
                name_el = await card.query_selector('[class*="name"], [class*="title"], h3, h4, .product-name, .product-title')
                name = await name_el.inner_text() if name_el else ""

                # Try to extract price
                price_el = await card.query_selector('[class*="price"], [class*="value"], .price, .valor')
                price_text = await price_el.inner_text() if price_el else ""

                # Try to extract unit
                unit_el = await card.query_selector('[class*="unit"], [class*="unidade"], [class*="peso"]')
                unit_text = await unit_el.inner_text() if unit_el else ""

                if not name or len(name.strip()) < 3:
                    continue

                price = self._parse_price(price_text)
                if price is None:
                    continue

                unit = self._extract_unit(name, unit_text)

                products.append({
                    "product": name.strip(),
                    "price": price,
                    "unit": unit,
                    "validity_raw": "",
                    "brand": "",
                })

            except Exception as e:
                logger.debug("Erro ao extrair produto: %s", e)
                continue

        return products

    def _parse_price(self, text: str) -> float | None:
        if not text:
            return None
        m = re.search(r"(?:R\$\s*)?([1-9]\d{0,2}(?:\.\d{3})*\s*,\d{2})\b", text.replace(".", "").replace(",", "."))
        if m:
            try:
                return float(m.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                pass
        return None

    def _extract_unit(self, name: str, unit_text: str = "") -> str:
        combined = f"{name} {unit_text}"
        # Try to extract unit from name or unit_text
        import re
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|un|unidades|cx|pct|pacote)", combined, re.I)
        if m:
            return f"{m.group(1)} {m.group(2).lower()}"
        return "un"

    async def _fetch_page(self) -> str:
        """Busca e renderiza a página de ofertas."""
        pool = await get_browser_pool()
        browser = pool.browser
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        try:
            await page.goto(self.BASE_URL, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)
            html = await page.content()
            return html
        finally:
            await context.close()

    async def run_async(self) -> list[dict]:
        """Executa o scraper de forma assíncrona."""
        pool = await get_browser_pool()
        browser = pool.browser
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        try:
            page = await context.new_page()
            await page.goto(self.BASE_URL, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)
            products = await self._extract_products(page)
            return products
        finally:
            await context.close()

    def run(self, ingredients: list[dict]) -> list[dict]:
        return asyncio.run(self.run_async())


class RoldaoFlyerScraperSync:
    """Wrapper síncrono para compatibilidade com a pipeline."""

    def __init__(self, store_config: dict):
        self.scraper = RoldaoFlyerScraper(store_config)

    def run(self, ingredients: list[dict]) -> list[dict]:
        return self.scraper.run(ingredients)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass
