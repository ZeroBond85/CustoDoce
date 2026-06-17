import re
import time

import httpx


class VtexScraper:
    def __init__(self, store_config: dict):
        self.store = store_config
        self.name = store_config["name"]
        self.base_url = store_config["base_url"].rstrip("/")
        self.api_endpoint = (
            store_config.get("api_endpoint")
            or f"{self.base_url}/api/catalog_system/pub/products/search"
        )
        self.session = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        )

    def search_products(self, query: str) -> list[dict]:
        try:
            resp = self.session.get(
                self.api_endpoint,
                params={"ft": query},
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"[VtexScraper/{self.name}] Error searching '{query}': {e}")
            return []

    def parse_product(self, product: dict) -> list[dict]:
        entries = []
        product_name = product.get("productName", "")
        items = product.get("items", [])

        for item in items:
            item_name = (
                item.get("nameComplete")
                or item.get("name")
                or product_name
            )
            sellers = item.get("sellers", [])
            for seller in sellers:
                offer = seller.get("commertialOffer", {})
                price = offer.get("Price")
                if price is None or price <= 0:
                    continue
                available = offer.get("AvailableQuantity", 0)
                if available <= 0:
                    continue

                unit = self._extract_unit(item_name)
                validity_raw = offer.get("priceValidUntil", "")
                entries.append({
                    "product": item_name,
                    "price": float(price),
                    "unit": unit,
                    "validity_raw": validity_raw,
                })
        return entries

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
            results = self.search_products(query)
            if not results:
                aliases = ing.get("aliases", [])
                if aliases:
                    alias_query = aliases[0].lower()
                    results = self.search_products(alias_query)
            if not results:
                continue

            for prod in results:
                parsed = self.parse_product(prod)
                for entry in parsed:
                    all_entries.append({
                        "product": entry["product"],
                        "price": entry["price"],
                        "unit": entry["unit"],
                        "validity_raw": entry.get("validity_raw", ""),
                    })

            time.sleep(0.5)

        return all_entries
