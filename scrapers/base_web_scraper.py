import time
from abc import ABC, abstractmethod
from urllib.parse import quote

import httpx

from services.logger import logger


def _retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0):
    """Decorator para retry com backoff exponencial. Retorna None se todas falharem."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as e:
                    if attempt < max_retries:
                        delay = min(base_delay * (2**attempt), max_delay)
                        logger.warning(
                            "[%s] Tentativa %d/%d falhou: %s. Aguardando %.1fs...",
                            args[0].name if args else "scraper",
                            attempt + 1,
                            max_retries + 1,
                            e,
                            delay,
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            "[%s] Todas %d tentativas falharam: %s. Retornando None.",
                            args[0].name if args else "scraper",
                            max_retries + 1,
                            e,
                        )
            return None

        return wrapper

    return decorator


DEFAULT_SELECTORS: dict = {
    "product_card": [
        ".product-item",
        ".product",
        ".produto",
        "li.product",
        "article.product",
        ".item",
        ".product-card",
        ".product-box",
        "[class*=produto]",
        "[class*=product]",
    ],
    "product_name": [
        "h2 a",
        "h3 a",
        ".product-name a",
        ".product-name",
        ".nome-produto",
        ".name a",
        "a[class*=name]",
        "a[class*=nome]",
        "[class*=title] a",
        ".product-title a",
    ],
    "product_price": [
        ".price",
        ".preco",
        ".current-price",
        "span.price",
        ".product-price",
        "[class*=price]",
        "[class*=preco]",
        ".sale-price",
        ".offer-price",
        ".box-price",
    ],
    "product_validity": [],
    "product_brand": [],
}


class BaseWebScraper(ABC):
    DEFAULT_RATE_LIMIT = 1.0
    DEFAULT_MAX_RETRIES = 3

    def __init__(self, store_config: dict, rate_limit: float | None = None, max_retries: int | None = None):
        self.store = store_config
        self.name = store_config.get("name", "unknown")
        self.base_url = (store_config.get("base_url") or "").rstrip("/")
        self.rate_limit = rate_limit or store_config.get("rate_limit", self.DEFAULT_RATE_LIMIT)
        self.max_retries = max_retries or store_config.get("max_retries", self.DEFAULT_MAX_RETRIES)

        # Headers customizáveis por store
        custom_headers = store_config.get("headers", {})
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        headers.update(custom_headers)

        # SSL verification (pode ser desabilitado para sites com certificado problemático)
        verify_ssl = store_config.get("verify_ssl", True)

        self._http = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers=headers,
            verify=verify_ssl,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._http.close()

    def close(self):
        self._http.close()

    # ─── Sprint 4: Self-Healing Hooks (Licao #15) ────────────────────
    # Subclasses MUST call these helpers from their failure / success paths.
    # The scraper_health module records persistence state, controls
    # auto-disable / re-activation and is the single entry point that the
    # heal-scrapers cron job audits (every 15 days).

    @property
    def store_name(self) -> str:
        """Public accessor used by self-healing hooks."""
        return self.name

    def report_failure(self, reason: str, items_found: int = 0, products_matched: int = 0) -> dict:
        """Report a single failure to services.scraper_health.

        Subclasses call this from their except branches. Errors here are
        swallowed because health-tracking must never interrupt the pipeline.
        """
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
        """Report a successful execution (resets failure counter)."""
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

    @_retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=30.0)
    def fetch_search(self, query: str) -> str | None:
        search_url = self.store.get("search_url", "").format(query=quote(query))
        if not search_url:
            return None
        resp = self._http.get(search_url)
        resp.raise_for_status()
        return resp.text

    @_retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=30.0)
    def fetch_json(self, url: str, params: dict | None = None) -> dict | list | None:
        resp = self._http.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def _throttle(self):
        if self.rate_limit > 0:
            time.sleep(self.rate_limit)

    @abstractmethod
    def parse_products(self, raw_data) -> list[dict]: ...

    def run(self, ingredients: list[dict]) -> list[dict]:
        all_entries = []
        for ing in ingredients:
            entries = self._search_and_parse(ing)
            all_entries.extend(entries)
            self._throttle()
        return all_entries

    def _search_and_parse(self, ing: dict) -> list[dict]:
        html = None
        for term in ing.get("search_terms", []):
            html = self.fetch_search(term.lower())
            if html:
                break
        if not html:
            html = self.fetch_search(ing["canonical_name"].lower())
        if not html:
            for alias in ing.get("aliases", []):
                html = self.fetch_search(alias.lower())
                if html:
                    break
        if not html:
            return []
        return self.parse_products(html)
