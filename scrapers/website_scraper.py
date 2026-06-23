import logging
import re
from urllib.parse import quote

from selectolax.parser import HTMLParser

from parsers.unit_extractor import extract_unit
from scrapers.base_web_scraper import BaseWebScraper

logger = logging.getLogger(__name__)

DEFAULT_SELECTORS = {
    "product_card": [
        ".product-item", ".product", ".produto",
        "li.product", "article.product",
        ".item", ".product-card", ".product-box",
        "[class*=produto]", "[class*=product]",
    ],
    "product_name": [
        "h2 a", "h3 a", ".product-name a", ".product-name",
        ".nome-produto", ".name a",
        "a[class*=name]", "a[class*=nome]",
        "[class*=title] a", ".product-title a",
    ],
    "product_price": [
        ".price", ".preco", ".current-price",
        "span.price", ".product-price",
        "[class*=price]", "[class*=preco]",
        ".sale-price", ".offer-price", ".box-price",
    ],
    "product_validity": [],
    "product_brand": [],
}


class WebsiteScraper(BaseWebScraper):

    def __init__(self, store_config: dict):
        super().__init__(store_config)
        self.search_url = (
            store_config.get("search_url")
            or f"{self.base_url}/busca?q={{query}}"
        )
        self.selectors = {**DEFAULT_SELECTORS, **store_config.get("selectors", {})}

    def fetch_search(self, query: str) -> str | None:
        url = self.search_url.format(query=quote(query))
        try:
            resp = self._http.get(url)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.warning("[%s] Error fetching '%s': %s", self.name, url, e)
            return None

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
            validity = self._extract_validity(card)
            brand = self._extract_brand(card)
            products.append({
                "product": name.strip(),
                "price": price,
                "unit": unit,
                "validity_raw": validity,
                "brand": brand,
            })

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
        m = re.search(r"[\d.,]+", text.replace(" ", "").replace(".", "").replace(",", "."))
        if m:
            try:
                return float(m.group())
            except ValueError:
                pass
        return None

    def _extract_brand(self, node) -> str:
        for selector in self.selectors.get("product_brand", []):
            found = node.css(selector)
            if found:
                text = found[0].text().strip()
                if text:
                    return text
        return ""

    def _extract_validity(self, node) -> str:
        for selector in self.selectors.get("product_validity", []):
            found = node.css(selector)
            if found:
                text = found[0].text().strip()
                if text:
                    return text
        return ""
