import re
import time
from urllib.parse import quote

import httpx
from selectolax.parser import HTMLParser


class CarrefourScraper:
    def __init__(self, store_config: dict):
        self.store = store_config
        self.name = store_config["name"]
        self.base_url = store_config["base_url"].rstrip("/")
        self.search_url = store_config.get("search_url") or f"{self.base_url}/busca?q={{query}}"
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
        self._price_re = re.compile(r"R\$\s*(\d+(?:[.,]\d{2}))")

    def fetch_search(self, query: str) -> str | None:
        url = self.search_url.format(query=quote(query))
        try:
            resp = self.session.get(url)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"[Carrefour] Error fetching '{url}': {e}")
            return None

    def parse_products(self, html: str) -> list[dict]:
        tree = HTMLParser(html)
        products = []

        for link in tree.css('a[href*="/produto/"]'):
            text = link.text(strip=True)
            price_match = self._price_re.search(text)
            if not price_match:
                continue

            price_str = price_match.group(1).replace(",", ".")
            try:
                price = float(price_str)
            except ValueError:
                continue
            if price <= 0 or price >= 10000:
                continue

            product_name = self._price_re.sub("", text).strip()
            product_name = re.sub(r"(Patrocinado|Adicionar|Comprar)", "", product_name, flags=re.I).strip()
            product_name = re.sub(r"\s+", " ", product_name).strip()

            products.append({
                "product": product_name,
                "price": price,
                "unit": self._extract_unit(product_name + " " + link.attributes.get("href", "")),
            })

        return products

    def _extract_unit(self, text: str) -> str:
        patterns = [
            r"(\d+\s*x\s*[\d.,]+\s*(?:kg|g|ml|un|L|l))",
            r"([\d.,]+\s*(?:kg|g|ml|un|L|l)\b)",
            r"(cx\s*(?:com\s*)?\d+)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if m:
                return m.group(1).strip()
        return ""

    def run(self, ingredients: list[dict]) -> list[dict]:
        all_entries = []

        for ing in ingredients:
            query = ing["canonical"].lower().replace("%", " ")
            html = self.fetch_search(query)
            if not html:
                continue

            results = self.parse_products(html)
            for entry in results:
                all_entries.append(entry)

            time.sleep(1.0)

        return all_entries
