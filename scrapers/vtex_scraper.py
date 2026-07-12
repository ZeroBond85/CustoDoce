from parsers.brand_extractor import extract_brand
from parsers.unit_extractor import extract_unit
from scrapers.base_web_scraper import BaseWebScraper
from services.logger import logger


class VtexScraper(BaseWebScraper):
    def __init__(self, store_config: dict):
        super().__init__(store_config, rate_limit=0.5)
        self.api_endpoint = (
            store_config.get("api_endpoint") or f"{self.base_url}/api/catalog_system/pub/products/search"
        )

    def _search_and_parse(self, ing: dict) -> list[dict]:
        ing_name = ing.get("canonical_name", "?")
        results = []
        for term in ing.get("search_terms", []):
            logger.info("[%s] Searching term '%s' for '%s'", self.name, term, ing_name)
            results = self._fetch_products(term.lower())
            if results:
                logger.info("[%s] Found %d results via term '%s'", self.name, len(results), term)
                break
        if not results:
            logger.info("[%s] Fallback: canonical '%s'", self.name, ing_name)
            results = self._fetch_products(ing_name.lower())
        if not results:
            for alias in ing.get("aliases", []):
                logger.info("[%s] Fallback: alias '%s'", self.name, alias)
                results = self._fetch_products(alias.lower())
                if results:
                    logger.info("[%s] Found %d results via alias '%s'", self.name, len(results), alias)
                    break
        if not results:
            logger.info("[%s] No results for '%s'", self.name, ing_name)
            return []
        entries = []
        for prod in results:
            entries.extend(self.parse_product(prod, ing))
        logger.info("[%s] Parsed %d entries for '%s'", self.name, len(entries), ing_name)
        return entries

    def _fetch_products(
        self, query: str, page_size: int = 50, max_pages: int = 10, timeout_total: int = 30
    ) -> list[dict]:
        """Busca produtos com paginação. Loga progresso periodicamente."""
        import time as _time
        from urllib.parse import quote

        all_results = []
        page = 1
        start = _time.time()
        last_log = start
        log_interval = 10.0
        try:
            while page <= max_pages:
                elapsed = _time.time() - start
                if elapsed > timeout_total:
                    logger.warning(
                        "[%s] Timeout (%ds) excedido para '%s' — %d páginas, %d resultados",
                        self.name, timeout_total, query, page - 1, len(all_results),
                    )
                    break
                resp = self._http.get(
                    f"{self.api_endpoint}/{quote(query)}", params={"page": page, "page_size": page_size}
                )
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list) or not data:
                    logger.info("[%s] Empty response at page %d for '%s'", self.name, page, query)
                    break
                all_results.extend(data)
                now = _time.time()
                if now - last_log >= log_interval:
                    logger.info(
                        "[%s] '%s': page %d/%d, %d results, %.1fs elapsed",
                        self.name, query, page, max_pages, len(all_results), now - start,
                    )
                    last_log = now
                if len(data) < page_size:
                    break
                page += 1
                if self.rate_limit > 0:
                    _time.sleep(self.rate_limit)
        except Exception as e:
            logger.warning("[%s] Error searching '%s' (page %d): %s", self.name, query, page, e)
        total = _time.time() - start
        logger.info("[%s] '%s' done: %d results in %.1fs", self.name, query, len(all_results), total)
        return all_results

    def parse_product(self, product: dict, ing: dict) -> list[dict]:
        entries = []
        product_name = product.get("productName", "")
        brand_api = product.get("brand", "")
        items = product.get("items", [])

        for item in items:
            item_name = item.get("nameComplete") or item.get("name") or product_name
            extracted = extract_brand(item_name, ing)
            brand = extracted if extracted != "Desconhecido" else brand_api
            sellers = item.get("sellers", [])
            for seller in sellers:
                offer = seller.get("commertialOffer", {})
                price = offer.get("Price")
                if price is None or price <= 0:
                    continue
                available = offer.get("AvailableQuantity", 0)
                if available <= 0:
                    continue

                unit = extract_unit(item_name)
                validity_raw = offer.get("priceValidUntil", "")
                entries.append(
                    {
                        "product": item_name,
                        "price": float(price),
                        "unit": unit,
                        "validity_raw": validity_raw,
                        "brand": brand,
                    }
                )
        return entries

    def parse_products(self, raw_data) -> list[dict]:
        return []
