import re
import time
from urllib.parse import quote

import httpx
from selectolax.parser import HTMLParser


DEFAULT_SELECTORS = {
    "product_card": [
        ".product-item", ".product", ".produto",
        "li.product", "article.product",
        ".item", ".product-card", ".product-box",
        "[class*=produto]", "[class*=product]",
    ],
    "product_name": [
        "h2 a", "h3 a", ".product-name a",
        ".nome-produto", ".name a",
        "a[class*=name]", "a[class*=nome]",
        "[class*=title] a", ".product-title a",
    ],
    "product_price": [
        ".price", ".preco", ".current-price",
        "span.price", ".product-price",
        "[class*=price]", "[class*=preco]",
        ".sale-price", ".offer-price",
    ],
}


class WebsiteScraper:
    def __init__(self, store_config: dict):
        self.store = store_config
        self.name = store_config["name"]
        self.base_url = store_config["base_url"].rstrip("/")
        self.search_url = (
            store_config.get("search_url")
            or f"{self.base_url}/busca?q={{query}}"
        )
        self.selectors = {**DEFAULT_SELECTORS, **store_config.get("selectors", {})}
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

    def fetch_search(self, query: str) -> str | None:
        url = self.search_url.format(query=quote(query))
        try:
            resp = self.session.get(url)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"[WebsiteScraper/{self.name}] Error fetching '{url}': {e}")
            return None

    def parse_results(self, html: str) -> list[dict]:
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
            unit = self._extract_unit(name)
            products.append({
                "product": name.strip(),
                "price": price,
                "unit": unit,
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

    def _parse_price(self, text: str) -> float | None:
        m = re.search(r"[\d.,]+", text.replace(".", "").replace(",", "."))
        if m:
            try:
                return float(m.group())
            except ValueError:
                pass
        return None

    def _extract_unit(self, name: str) -> str:
        patterns = [
            r"(\d+\s*x\s*[\d.,]+\s*(?:kg|g|ml|un))",
            r"([\d.,]+\s*(?:kg|g|ml|un)\b)",
            r"(cx\s*(?:com\s*)?\d+)",
        ]
        for pat in patterns:
            m = re.search(pat, name, re.I)
            if m:
                return m.group(1).strip()
        return ""

    def run(self, ingredients: list[dict]) -> list[dict]:
        all_entries = []

        for ing in ingredients:
            query = ing["canonical"].lower()
            html = self.fetch_search(query)
            if not html:
                aliases = ing.get("aliases", [])
                if aliases:
                    html = self.fetch_search(aliases[0].lower())
            if not html:
                continue

            results = self.parse_results(html)
            for entry in results:
                all_entries.append(entry)

            time.sleep(1.0)

        return all_entries
