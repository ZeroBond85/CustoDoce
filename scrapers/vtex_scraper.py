from scrapers.base_web_scraper import BaseWebScraper
from services.logger import logger
from parsers.brand_extractor import extract_brand
from parsers.unit_extractor import extract_unit


class VtexScraper(BaseWebScraper):
    def __init__(self, store_config: dict):
        super().__init__(store_config, rate_limit=0.5)
        self.api_endpoint = (
            store_config.get("api_endpoint") or f"{self.base_url}/api/catalog_system/pub/products/search"
        )

    def _search_and_parse(self, ing: dict) -> list[dict]:
        results = []
        for term in ing.get("search_terms", []):
            results = self._fetch_products(term.lower())
            if results:
                break
        if not results:
            results = self._fetch_products(ing["canonical_name"].lower())
        if not results:
            for alias in ing.get("aliases", []):
                results = self._fetch_products(alias.lower())
                if results:
                    break
        if not results:
            return []
        entries = []
        for prod in results:
            entries.extend(self.parse_product(prod, ing))
        return entries

    def _fetch_products(
        self, query: str, page_size: int = 100, max_pages: int = 20, timeout_total: int = 60
    ) -> list[dict]:
        """Busca produtos com paginação para obter todos os resultados."""
        from urllib.parse import quote
        import time as _time

        all_results = []
        page = 1
        start = _time.time()
        try:
            while page <= max_pages:
                if _time.time() - start > timeout_total:
                    logger.warning("[%s] Timeout total (%ds) atingido para '%s'", self.name, query, timeout_total)
                    break
                resp = self._http.get(
                    f"{self.api_endpoint}/{quote(query)}", params={"page": page, "page_size": page_size}
                )
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list) or not data:
                    break
                all_results.extend(data)
                if len(data) < page_size:
                    break
                page += 1
                if self.rate_limit > 0:
                    _time.sleep(self.rate_limit)
        except Exception as e:
            logger.warning("[%s] Error searching '%s': %s", self.name, query, e)
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
