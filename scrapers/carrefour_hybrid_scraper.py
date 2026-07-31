"""Carrefour Mercado Hybrid Scraper — GraphQL first, HTML category fallback.

Tenta GraphQL (rápido). Se 403/429 → HTML category pages + busca.
"""

import re
import time
from urllib.parse import quote

from selectolax.parser import HTMLParser

from parsers.unit_extractor import extract_unit
from scrapers.base_web_scraper import BaseWebScraper
from services.logger import logger


class CarrefourHybridScraper(BaseWebScraper):
    """Scraper híbrido: GraphQL → HTML category/search fallback."""

    def __init__(self, store_config: dict):
        super().__init__(store_config)
        self.graphql_endpoint = store_config.get(
            "graphql_endpoint",
            "https://mercado.carrefour.com.br/_v/segment/graphql/v1",
        )
        self.category_urls = store_config.get("category_urls", [])
        self.search_url = store_config.get("search_url")
        self.pagination = store_config.get("pagination", "?sort=orders_desc&page={page}")
        self.max_pages_per_category = int(store_config.get("max_pages_per_category", 5))
        self.graphql_headers = store_config.get("headers_custom", {})
        self.use_graphql = store_config.get("use_graphql", True)
        self._graphql_failed = False

        # Selectors para HTML
        selectors = store_config.get("selectors", {})
        self.selectors = {
            "product_card": selectors.get("product_card", [
                '[data-testid="search-product-card"]',
                '[data-testid="highlight-product-card"]',
                '[data-testid="product-card"]',
                ".product-card",
                ".product",
                ".product-item",
                "[class*='product-card']",
                "[class*='ProductCard']",
                "article.product",
            ]),
            "product_name": selectors.get("product_name", [
                '[data-testid="product-name"]',
                "h2",
                "h3",
                ".product-title",
                ".product-name",
                "[class*='product-name']",
                "[class*='ProductName']",
            ]),
            "product_price": selectors.get("product_price", [
                ".text-price-default",
                '[data-testid="product-price"]',
                ".price",
                ".product-price",
                "[class*='price']",
                "[class*='Price']",
            ]),
            "product_brand": selectors.get("product_brand", [
                '[data-testid="product-brand"]',
                ".brand",
                ".product-brand",
                "[class*='brand']",
            ]),
        }

    def run(self, ingredients: list[dict]) -> list[dict]:
        """Coleta via GraphQL; se falhar, HTML category + search."""
        if self.use_graphql and not self._graphql_failed:
            results = self._run_graphql(ingredients)
            if results:
                return results
            logger.warning("[%s] GraphQL falhou → fallback HTML", self.name)
            self._graphql_failed = True

        return self._run_html(ingredients)

    # ─── GraphQL ──────────────────────────────────────────────────────

    def _run_graphql(self, ingredients: list[dict]) -> list[dict]:
        """Tenta GraphQL para todos os ingredientes."""
        all_entries: list[dict] = []

        for ing in ingredients:
            entries = self._graphql_search_ingredient(ing)
            all_entries.extend(entries)
            self._throttle()

        return all_entries

    def _graphql_search_ingredient(self, ing: dict) -> list[dict]:
        """Busca um ingrediente via GraphQL tentando múltiplos termos."""
        terms = ing.get("search_terms", []) + [ing["canonical_name"]] + ing.get("aliases", [])

        for term in terms:
            entries = self._graphql_query(term)
            if entries:
                return entries

        return []

    def _graphql_query(self, query: str) -> list[dict]:
        """Executa uma query GraphQL."""
        graphql_query = """
        query SearchProducts($term: String!, $first: Int!) {
            search(term: $term, first: $first) {
                products {
                    edges {
                        node {
                            id
                            name
                            priceRange { minVariantPrice { amount } }
                            brand { name }
                            description
                        }
                    }
                }
            }
        }
        """

        payload = {
            "query": graphql_query.strip(),
            "variables": {"term": query, "first": 50},
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            **self.graphql_headers,
        }

        try:
            resp = self._http.post(
                self.graphql_endpoint,
                json=payload,
                headers=headers,
                timeout=30.0,
            )

            if resp.status_code == 403:
                logger.warning("[%s] GraphQL 403", self.name)
                return []
            if resp.status_code == 429:
                logger.warning("[%s] GraphQL 429", self.name)
                return []

            resp.raise_for_status()
            data = resp.json()

            products = data.get("data", {}).get("search", {}).get("products", {}).get("edges", [])
            return [self._parse_graphql_product(p["node"]) for p in products if p.get("node")]

        except Exception as e:
            logger.error("[%s] GraphQL query falhou: %s", self.name, e)
            return []

    def _parse_graphql_product(self, node: dict) -> dict | None:
        """Converte produto GraphQL no formato padrão."""
        name = (node.get("name") or "").strip()
        price_info = node.get("priceRange", {}).get("minVariantPrice", {})
        price = price_info.get("amount")

        if not name or price is None:
            return None

        try:
            price = float(price)
        except (TypeError, ValueError):
            return None

        if price <= 0 or price >= 10000:
            return None

        brand = (node.get("brand", {}).get("name") or "").strip()
        description = (node.get("description") or "").strip()

        return {
            "product": name,
            "price": price,
            "unit": extract_unit(name + " " + description),
            "validity_raw": "",
            "brand": brand,
        }

    # ─── HTML Category/Search ────────────────────────────────────────

    def _run_html(self, ingredients: list[dict]) -> list[dict]:
        """Fallback HTML: category pages + search."""
        all_entries: list[dict] = []

        # 1. Category pages
        if self.category_urls:
            for url in self.category_urls:
                entries = self._scrape_category_pages(url)
                all_entries.extend(entries)
                if len(all_entries) > 200:  # limite de segurança
                    break

        # 2. Search para ingredientes não cobertos por categorias
        if self.search_url:
            search_entries = self._search_missing_ingredients(ingredients, all_entries)
            all_entries.extend(search_entries)

        return all_entries

    def _scrape_category_pages(self, base_url: str) -> list[dict]:
        """Raspa páginas de categoria com paginação."""
        entries: list[dict] = []

        for page in range(self.max_pages_per_category):
            url = base_url + self.pagination.format(page=page)
            logger.info("[%s] Category page %d: %s", self.name, page + 1, url)

            html = self._fetch_html(url)
            if not html:
                break

            page_entries = self._parse_html_products(html)
            if not page_entries:
                break

            entries.extend(page_entries)

            # Se a página tem poucos produtos, provavelmente acabou
            if len(page_entries) < 10:
                break

            self._throttle()

        return entries

    def _search_missing_ingredients(self, ingredients: list[dict], existing_entries: list[dict]) -> list[dict]:
        """Busca ingredientes que não foram bem cobertos por categorias."""
        # Ingredientes já cobertos (pelo nome do produto)
        covered_terms = set()
        for entry in existing_entries:
            name = entry.get("product", "").lower()
            for ing in ingredients:
                for term in [ing["canonical_name"]] + ing.get("search_terms", []) + ing.get("aliases", []):
                    if term.lower() in name:
                        covered_terms.add(term.lower())

        missing_entries: list[dict] = []
        for ing in ingredients:
            terms = [ing["canonical_name"]] + ing.get("search_terms", []) + ing.get("aliases", [])
            if any(t.lower() in covered_terms for t in terms):
                continue

            for term in terms:
                entries = self._search_html(term)
                if entries:
                    missing_entries.extend(entries)
                    break

        return missing_entries

    def _search_html(self, query: str) -> list[dict]:
        """Busca HTML via search_url.

        O Carrefour redireciona ``/busca?q=`` para ``/busca/{query}`` e retorna
        500 quando o path contem ``%25`` (query original com ``%``, ex.:
        "Creme de Leite 20%"). Sanitiza o ``%`` antes de montar a URL.
        """
        if not self.search_url:
            return []

        # Carrefour 500 em busca com '%' (ex: "Chocolate 70%") — remove o char
        cleaned = re.sub(r"%", "", query).strip()
        if not cleaned:
            return []

        url = self.search_url.format(query=quote(cleaned))
        html = self._fetch_html(url)
        if not html:
            return []

        return self._parse_html_products(html)

    def _fetch_html(self, url: str) -> str | None:
        """Busca HTML com retry."""
        for attempt in range(3):
            try:
                resp = self._http.get(url, timeout=30.0)
                if resp.status_code == 403:
                    logger.warning("[%s] HTML 403: %s", self.name, url)
                    return ""
                if resp.status_code == 429:
                    logger.warning("[%s] HTML 429: %s", self.name, url)
                    time.sleep(2 ** attempt)
                    continue

                resp.raise_for_status()
                return resp.text
            except Exception as e:
                logger.error("[%s] HTML fetch falhou %s: %s", self.name, url, e)
                if attempt < 2:
                    time.sleep(2 ** attempt)

        return None

    def _parse_html_products(self, html: str) -> list[dict]:
        """Parseia produtos do HTML."""
        tree = HTMLParser(html)
        entries: list[dict] = []

        # Tenta seletores de card
        cards = []
        for selector in self.selectors["product_card"]:
            cards = tree.css(selector)
            if cards:
                break

        if not cards:
            return entries

        for card in cards:
            try:
                # Nome
                name = ""
                for selector in self.selectors["product_name"]:
                    el = card.css_first(selector)
                    if el:
                        name = el.text(strip=True)
                        break

                if not name:
                    continue

                # Preço
                price = None
                for selector in self.selectors["product_price"]:
                    el = card.css_first(selector)
                    if el:
                        price_text = el.text(strip=True)
                        price = self._parse_price(price_text)
                        if price:
                            break

                if price is None or price <= 0 or price >= 10000:
                    continue

                # Brand
                brand = ""
                for selector in self.selectors["product_brand"]:
                    el = card.css_first(selector)
                    if el:
                        brand = el.text(strip=True)
                        break

                entries.append({
                    "product": name,
                    "price": price,
                    "unit": extract_unit(name),
                    "validity_raw": "",
                    "brand": brand,
                })

            except Exception as e:
                logger.debug("[%s] Erro parseando card: %s", self.name, e)
                continue

        return entries

    def _parse_price(self, text: str) -> float | None:
        """Extrai preço do texto."""
        m = re.search(r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)", text)
        if m:
            raw = m.group(1).replace(".", "").replace(",", ".")
            try:
                return float(raw)
            except ValueError:
                pass
        return None

    def _throttle(self):
        if self.rate_limit > 0:
            time.sleep(self.rate_limit)

    # Required by BaseWebScraper abstract interface
    def parse_products(self, raw_data: str) -> list[dict]:
        """Delegate to HTML parser — used in fallback paths."""
        return self._parse_html_products(raw_data)
