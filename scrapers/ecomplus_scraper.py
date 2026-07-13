"""E-com.plus / cloudcommerce storefront scraper (BarraDoce e similares).

The storefront renders products server-side (SSR): product cards are plain
HTML anchors, so we can scrape with httpx + selectolax (no headless browser).
This is dramatically faster than the Playwright path and fits the CI budget.

Access methods explored:
  * Search:        {base}/s?q={query}   (SSR, ~48 cards/page)
  * Category:      {base}/categoria/{slug}?p=N  (SSR, paginated via ?p=)
  * Listings:      {base}/p/promocoes , /p/lancamentos (SSR)
Product card markup (e-com.plus theme):
  <a href="/produto/..." class="flex h-full flex-col overflow-hidden ...">
     <span class="uno-zmd234"> -<strong>80</strong>% </span>   # discount (promo only)
     <div class="... text-base-600 ...">
        <s>R$ 14,80</s>                                        # old price (struck)
        <strong class="... text-base-800"> R$ 2,96</strong>   # CURRENT price
     </div>
     <h5 ...>Product Name</h5>
"""


from selectolax.parser import HTMLParser

from parsers.unit_extractor import extract_unit
from scrapers.base_web_scraper import DEFAULT_SELECTORS, BaseWebScraper
from services.logger import logger

ECOMPLUS_SELECTORS: dict = {
    "product_card": ["a[href^='/produto/']"],
    # The e-com.plus theme uses different heading tags per template:
    #   * category/listing pages  -> <h3 class="...ui-link...">
    #   * search results / detail -> <h5 class="...ui-link...">
    "product_name": ["h3.ui-link", "h5.ui-link", "h3", "h5", "a.ui-link"],
    "product_price": ["strong.text-base-800"],
    "product_old_price": ["s"],
    "product_discount": ["span.uno-zmd234"],
    "product_brand": [],
    "product_validity": [],
}


class EcomplusScraper(BaseWebScraper):
    def __init__(self, store_config: dict, rate_limit: float | None = None, max_retries: int | None = None):
        super().__init__(store_config, rate_limit=rate_limit, max_retries=max_retries)
        self.search_url = store_config.get("search_url") or f"{self.base_url}/s?q={{query}}"
        self.browse_urls = list(store_config.get("browse_urls", []) or [])
        self.selectors = {**DEFAULT_SELECTORS, **ECOMPLUS_SELECTORS, **store_config.get("selectors", {})}
        self.max_pages = int(store_config.get("max_pages", 15))

    # ─── public API (mirrors WebsiteScraper) ──────────────────────────────
    def run(self, ingredients: list[dict]) -> list[dict]:
        products: list[dict] = []
        if self.browse_urls:
            logger.info("[%s] browse mode: %d URLs", self.name, len(self.browse_urls))
            for url in self.browse_urls:
                found = self._browse(url)
                logger.info("[%s] %d products from %s", self.name, len(found), url)
                products.extend(found)
                self._throttle()
        else:
            for ing in ingredients:
                for term in ing.get("search_terms", []) + [ing.get("canonical_name", "")] + ing.get("aliases", []):
                    if not term:
                        continue
                    html = self.fetch_search(term)
                    if html:
                        found = self.parse_products(html)
                        if found:
                            products.extend(found)
                            break
                self._throttle()
        return products

    def parse_products(self, html: str) -> list[dict]:
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
            href = card.attributes.get("href", "")
            source_url = f"{self.base_url}{href}" if href.startswith("/") else href
            old_price = self._extract_old_price(card)
            discount_pct = self._extract_discount(card)
            products.append(
                {
                    "product": name.strip(),
                    "price": price,
                    "old_price": old_price,
                    "discount_pct": discount_pct,
                    "unit": unit,
                    "validity_raw": "",
                    "brand": "",
                    "source_url": source_url,
                }
            )
        return products

    # ─── browse (paginated category / listing pages) ──────────────────────
    def _browse(self, base_url: str) -> list[dict]:
        all_products: list[dict] = []
        for page in range(1, self.max_pages + 1):
            url = f"{base_url}?p={page}" if page > 1 else base_url
            try:
                resp = self._http.get(url)
                resp.raise_for_status()
                html = resp.text
            except Exception as e:
                logger.warning("[%s] browse fetch failed %s: %s", self.name, url, e)
                break
            found = self.parse_products(html)
            if not found:
                break
            all_products.extend(found)
            # stop when we reach the last page (fewer items than a full page)
            if len(found) < 40:
                break
            self._throttle()
        return all_products

    # ─── selectors ────────────────────────────────────────────────────────
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
        # Preferred: current price is the <strong> with class text-base-800.
        for sel in self.selectors["product_price"]:
            els = node.css(sel)
            if els:
                price = self._parse_price(els[0].text())
                if price is not None:
                    return price
        # Fallback: last <strong> whose text actually contains "R$"
        # (the discount % strong has no "R$" and must be skipped).
        for c in reversed(node.css("strong")):
            txt = c.text() or ""
            if "R$" in txt:
                price = self._parse_price(txt)
                if price is not None:
                    return price
        return None

    def _extract_old_price(self, node) -> float | None:
        sel = self.selectors.get("product_old_price")
        if not sel:
            return None
        for s in sel:
            els = node.css(s)
            if els:
                price = self._parse_price(els[0].text())
                if price is not None:
                    return price
        return None

    def _extract_discount(self, node) -> int | None:
        sel = self.selectors.get("product_discount")
        if not sel:
            return None
        for s in sel:
            els = node.css(s)
            if els:
                txt = els[0].text() or ""
                import re

                m = re.search(r"(\d+)", txt)
                if m:
                    return int(m.group(1))
        return None

    @staticmethod
    def _parse_price(text: str) -> float | None:
        import re

        m = re.search(r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)", text)
        if m:
            raw = m.group(1).replace(".", "").replace(",", ".")
            try:
                return float(raw)
            except ValueError:
                pass
        return None
