import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

from selectolax.parser import HTMLParser

from parsers.unit_extractor import extract_unit
from scrapers.base_web_scraper import DEFAULT_SELECTORS, BaseWebScraper, _retry_with_backoff
from services.logger import logger


class WebsiteScraper(BaseWebScraper):
    # Scraper HTTP (requests) com timeouts por-URL: seguro no processo pai
    # (evita o spawn lento/no Windows que degrada as requisições).
    safe_in_parent = True

    def __init__(self, store_config: dict):
        super().__init__(store_config)
        self.search_url = store_config.get("search_url") or f"{self.base_url}/busca?q={{query}}"
        self.selectors = {**DEFAULT_SELECTORS, **store_config.get("selectors", {})}
        self.browse_parallel = store_config.get("browse_parallel", False)
        # Teto de parede por URL de browse: evita que UMA url lenta/travada
        # (Cloudflare, WAF) segure o loop paralelo inteiro. Default 30s.
        self.browse_url_timeout = float(store_config.get("browse_url_timeout", 30))

    def fetch_search(self, query: str) -> str | None:
        url = self.search_url.format(query=quote(query))
        try:
            resp = self._http.get(url)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.error("[%s] Error fetching '%s': %s", self.name, url, e)
            return None

    @_retry_with_backoff(max_retries=2, base_delay=2.0, max_delay=10.0)
    def _fetch_browse_raw(self, url: str) -> str | None:
        resp = self._http.get(url)
        resp.raise_for_status()
        return resp.text

    def fetch_browse(self, url: str) -> str | None:
        """Busca com teto de parede por URL (anti-travamento em Cloudflare/WAF)."""
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        if self.browse_url_timeout and self.browse_url_timeout > 0:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(self._fetch_browse_raw, url)
                try:
                    return fut.result(timeout=self.browse_url_timeout)
                except FuturesTimeout:
                    logger.warning(
                        "[%s] browse %s estourou teto de %ds (Cloudflare/WAF?) — ignorado",
                        self.name, url, int(self.browse_url_timeout),
                    )
                    return None
        return self._fetch_browse_raw(url)

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

        import time as _time
        start_ts = _time.time()
        logger.info("[%s] browse_urls mode: %d paginas de departamento", self.name, len(browse_urls))
        all_entries: list[dict] = []

        if self.browse_parallel:
            with ThreadPoolExecutor(max_workers=min(4, len(browse_urls))) as ex:
                url_map = {ex.submit(self.fetch_browse, url): url for url in browse_urls}
                for fut in as_completed(url_map):
                    url = url_map[fut]
                    html = fut.result()
                    if not html:
                        logger.warning("[%s] browse %s falhou (0 bytes)", self.name, url)
                        continue
                    found = self.parse_products(html)
                    logger.info("[%s] browse %s -> %d produtos", self.name, url, len(found))
                    all_entries.extend(found)
        else:
            for i, url in enumerate(browse_urls, 1):
                html = self.fetch_browse(url)
                self._throttle()
                if not html:
                    logger.warning("[%s] browse %d/%d vazio: %s", self.name, i, len(browse_urls), url)
                    continue
                found = self.parse_products(html)
                logger.info("[%s] browse %d/%d: %d produtos (%.1fs)", self.name, i, len(browse_urls), len(found), _time.time() - start_ts)
                all_entries.extend(found)
        logger.info("[%s] browse total: %d produtos em %.1fs", self.name, len(all_entries), _time.time() - start_ts)
        return all_entries

    def parse_products(self, html: str) -> list[dict]:
        products = self._parse_jsonld(html)
        if products:
            return products

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

    def _parse_jsonld(self, html: str) -> list[dict]:
        """Extrai produtos de JSON-LD embedado (VTEX IO / Schema.org)."""
        products: list[dict] = []
        m = re.findall(r'<script\s+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
        for block in m:
            try:
                data = json.loads(block.strip())
                items = []
                if data.get("@type") == "ItemList":
                    items = data.get("itemListElement", [])
                for entry in items:
                    item = entry.get("item", {})
                    if not item.get("name"):
                        continue
                    offers = item.get("offers", {})
                    price = offers.get("lowPrice") or offers.get("price") or 0
                    if price <= 0:
                        continue
                    name = item["name"].strip()
                    products.append({
                        "product": name,
                        "price": float(price),
                        "unit": extract_unit(name),
                        "validity_raw": "",
                        "brand": "",
                    })
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
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
