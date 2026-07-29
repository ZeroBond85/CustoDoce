from urllib.parse import quote

from parsers.unit_extractor import extract_unit
from scrapers.base_web_scraper import BaseWebScraper
from services.logger import logger


class CarrefourGraphQLScraper(BaseWebScraper):
    """Scraper para Carrefour Mercado via GraphQL API.

    Substitui o scraper HTML que recebia 403 Forbidden.
    Usa o endpoint GraphQL interno do VTEX IO.
    """

    safe_in_parent = True

    def __init__(self, store_config: dict):
        super().__init__(store_config)
        self.graphql_endpoint = store_config.get("graphql_endpoint")
        self.headers_custom = store_config.get("headers_custom", {})
        self.persist_cookies = store_config.get("persist_cookies", True)
        self.variables_template = store_config.get("graphql_variables_template", {})
        self._cookies = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._http.close()

    def close(self):
        self._http.close()

    @property
    def store_name(self) -> str:
        return self.name

    def _get_headers(self) -> dict:
        headers = dict(self._http.headers)
        headers.update(self.headers_custom)
        return headers

    def _get_variables(self, query: str) -> dict:
        vars = dict(self.variables_template)
        vars["term"] = vars.get("term", "{query}").format(query=quote(query))
        return vars

    def _graphql_query(self) -> str:
        return """
query SearchProducts($term: String!, $first: Int!, $after: String) {
  search(term: $term, first: $first, after: $after) {
    products {
      edges {
        node {
          id
          name
          priceRange {
            minVariantPrice {
              amount
              currency
            }
          }
          brand {
            name
          }
          description
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""

    def parse_products(self, html: str) -> list[dict]:
        """Parse HTML fallback (não usado no modo GraphQL)."""
        return []

    def run(self, ingredients: list[dict]) -> list[dict]:
        """Coleta preços via GraphQL para cada ingrediente."""
        all_entries: list[dict] = []

        for ing in ingredients:
            entries = self._search_and_parse(ing)
            all_entries.extend(entries)
            self._throttle()

        return all_entries

    def _search_and_parse(self, ing: dict) -> list[dict]:
        for term in ing.get("search_terms", []):
            entries = self._graphql_search(term)
            if entries:
                return entries
        entries = self._graphql_search(ing["canonical_name"])
        if entries:
            return entries
        for alias in ing.get("aliases", []):
            entries = self._graphql_search(alias)
            if entries:
                return entries
        return []

    def _graphql_search(self, query: str) -> list[dict]:
        variables = self._get_variables(query)
        payload = {
            "query": self._graphql_query(),
            "variables": variables,
        }

        try:
            resp = self._http.post(
                self.graphql_endpoint,
                json=payload,
                headers=self._get_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("[%s] GraphQL search falhou para '%s': %s", self.name, query, e)
            return []

        return self._parse_graphql_response(data, query)

    def _parse_graphql_response(self, data: dict, query: str) -> list[dict]:
        try:
            products_data = data.get("data", {}).get("search", {}).get("products", {})
            edges = products_data.get("edges", [])
        except Exception:
            return []

        entries: list[dict] = []
        for edge in edges:
            node = edge.get("node", {})
            name = (node.get("name") or "").strip()
            if not name:
                continue

            price_range = node.get("priceRange", {})
            min_price = price_range.get("minVariantPrice", {})
            price = min_price.get("amount")
            if price is None:
                continue

            try:
                price = float(price)
            except (TypeError, ValueError):
                continue
            if price <= 0 or price >= 10000:
                continue

            brand = node.get("brand", {}).get("name", "") or ""
            description = node.get("description", "") or ""

            unit = extract_unit(name + " " + description)
            entries.append(
                {
                    "product": name,
                    "price": price,
                    "unit": unit,
                    "validity_raw": "",
                    "brand": brand,
                }
            )

        logger.info("[%s] GraphQL '%s' -> %d produtos", self.name, query, len(entries))
        return entries

    def report_failure(self, reason: str, items_found: int = 0, products_matched: int = 0) -> dict:
        from contextlib import suppress
        from services.scraper_health import record_failure

        with suppress(Exception):
            return record_failure(
                self.store_name,
                reason=reason,
                items_found=items_found,
                products_matched=products_matched,
                flyer_count=0,
                attempted_by="collection_runner",
            )
        return {"recorded": False}

    def report_success(self, items_found: int, products_matched: int, flyer_count: int = 0) -> dict:
        from contextlib import suppress
        from services.scraper_health import record_success

        with suppress(Exception):
            return record_success(
                self.store_name,
                items_found=items_found,
                products_matched=products_matched,
                flyer_count=flyer_count,
                attempted_by="collection_runner",
            )
        return {"recorded": False}
