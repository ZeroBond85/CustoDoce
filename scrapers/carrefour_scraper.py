import logging
import re
from urllib.parse import quote

from selectolax.parser import HTMLParser

from parsers.unit_extractor import extract_unit
from scrapers.base_web_scraper import BaseWebScraper

logger = logging.getLogger(__name__)


class CarrefourScraper(BaseWebScraper):

    def __init__(self, store_config: dict):
        super().__init__(store_config)
        self.search_url = store_config.get("search_url") or f"{self.base_url}/busca?q={{query}}"
        self._price_re = re.compile(r"R\$\s*(\d+(?:\s*[.,]\s*\d{2})?)")

    def fetch_search(self, query: str) -> str | None:
        url = self.search_url.format(query=quote(query))
        try:
            resp = self._http.get(url)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.warning("[%s] Error fetching '%s': %s", self.name, url, e)
            return None

    def _search_and_parse(self, ing: dict) -> list[dict]:
        html = None
        for term in ing.get("search_terms", []):
            query = term.lower().replace("%", " ")
            html = self.fetch_search(query)
            if html:
                break
        if not html:
            html = self.fetch_search(ing["canonical_name"].lower().replace("%", " "))
        if not html:
            for alias in ing.get("aliases", []):
                html = self.fetch_search(alias.lower().replace("%", " "))
                if html:
                    break
        if not html:
            return []
        return self.parse_products(html)

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
                "unit": extract_unit(product_name + " " + link.attributes.get("href", "")),
                "validity_raw": "",
                "brand": "",
            })

        return products
