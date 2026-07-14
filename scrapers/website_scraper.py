import re
from urllib.parse import quote

from selectolax.parser import HTMLParser

from parsers.unit_extractor import extract_unit
from scrapers.base_web_scraper import DEFAULT_SELECTORS, BaseWebScraper
from services.logger import logger


class WebsiteScraper(BaseWebScraper):
    def __init__(self, store_config: dict):
        super().__init__(store_config)
        self.search_url = store_config.get("search_url") or f"{self.base_url}/busca?q={{query}}"
        self.selectors = {**DEFAULT_SELECTORS, **store_config.get("selectors", {})}

    def fetch_search(self, query: str) -> str | None:
        url = self.search_url.format(query=quote(query))
        try:
            resp = self._http.get(url)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.error("[%s] Error fetching '%s': %s", self.name, url, e)
            return None

    def fetch_browse(self, url: str) -> str | None:
        try:
            resp = self._http.get(url)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.error("[%s] Error fetching browse '%s': %s", self.name, url, e)
            return None

    def run(self, ingredients: list[dict]) -> list[dict]:
        """Coleta via browse_urls (departamentos) quando configurado.

        Para lojas SPA cuja busca nao renderiza (ex.: Lojas Integrada),
        as paginas de departamento sao server-rendered e muito mais rapidas
        que N buscas por ingrediente. Sem browse_urls, cai no padrao
        (1 busca por ingrediente).
        """
        browse_urls = self.store.get("browse_urls") or []
        if not browse_urls:
            return super().run(ingredients)

        logger.info("[%s] browse_urls mode: %d paginas de departamento", self.name, len(browse_urls))
        all_entries: list[dict] = []
        for i, url in enumerate(browse_urls, 1):
            html = self.fetch_browse(url)
            self._throttle()
            if not html:
                logger.warning("[%s] browse %d/%d vazio: %s", self.name, i, len(browse_urls), url)
                continue
            found = self.parse_products(html)
            logger.info("[%s] browse %d/%d: %d produtos", self.name, i, len(browse_urls), len(found))
            all_entries.extend(found)
        return all_entries

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
            products.append(
                {
                    "product": name.strip(),
                    "price": price,
                    "unit": unit,
                    "validity_raw": validity,
                    "brand": brand,
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
