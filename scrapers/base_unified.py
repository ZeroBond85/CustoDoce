from __future__ import annotations

import hashlib
import io
import time
from abc import ABC, abstractmethod

import httpx

from services.cache_manager import CacheManager
from services.error_classifier import classify_error
from services.logger import logger
from services.rate_limiter import TokenBucket, TokenBucketConfig
from services.retry_policy import RetryPolicy
from services.selector_resolver import resolve_selectors
from services.url_guard import make_safe_client


class BaseScraper(ABC):
    store: dict
    name: str
    _http: httpx.Client
    _token_bucket: TokenBucket
    _retry_policy: RetryPolicy
    _cache: CacheManager | None

    def __init__(
        self,
        store_config: dict,
        rate_limit: float | None = None,
        max_retries: int | None = None,
        cache_dir: str = "",
        use_cache: bool = True,
    ):
        self.store = store_config
        self.name = store_config.get("name", "unknown")
        self.scraper_type = store_config.get("type", "website_catalog")

        # Rate limiting — TokenBucket per store
        rl = rate_limit or store_config.get("rate_limit", 1.0)
        self._token_bucket = TokenBucket(
            TokenBucketConfig(capacity=rl, refill_rate=rl / 60.0)
        )

        # Retry policy
        mr = max_retries or store_config.get("max_retries", 3)
        self._retry_policy = RetryPolicy(max_retries=mr)

        # Selectors — resolved from selectors.yaml + store config
        self._selectors = resolve_selectors(store_config)

        # Cache
        self._cache = CacheManager(cache_dir=cache_dir) if use_cache else None

        # Headers
        anti_bot = store_config.get("anti_bot", False)
        if anti_bot:
            _UAS = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            ]
            chosen_ua = _UAS[hash(store_config.get("name", "")) % len(_UAS)]
        else:
            chosen_ua = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )

        headers = {
            "User-Agent": chosen_ua,
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
        }
        headers.update(store_config.get("headers", {}))

        to = store_config.get("http_timeout") or {}
        self._http_timeout = httpx.Timeout(
            connect=float(to.get("connect", 10.0)),
            read=float(to.get("read", 60.0)),
            pool=float(to.get("pool", 10.0)),
            write=float(to.get("write", 10.0)),
        )

        verify_ssl = store_config.get("verify_ssl", True)
        self._http = make_safe_client(
            timeout=self._http_timeout,
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

    @property
    def store_name(self) -> str:
        return self.name

    def report_failure(self, reason: str, items_found: int = 0, products_matched: int = 0, flyer_count: int = 0) -> dict:
        from contextlib import suppress
        from services.scraper_health import record_failure
        with suppress(Exception):
            return record_failure(
                self.store_name,
                reason=reason,
                items_found=items_found,
                products_matched=products_matched,
                flyer_count=flyer_count,
                attempted_by="unified_runner",
            )
        return {"recorded": False}

    def report_success(self, items_found: int, products_matched: int = 0, flyer_count: int = 0) -> dict:
        from contextlib import suppress
        from services.scraper_health import record_success
        with suppress(Exception):
            return record_success(
                self.store_name,
                items_found=items_found,
                products_matched=products_matched,
                flyer_count=flyer_count,
                attempted_by="unified_runner",
            )
        return {"recorded": False}

    def _throttle(self, key: str = ""):
        bucket_key = key or self.name
        if not self._token_bucket.consume(bucket_key):
            wait = self._token_bucket.wait_time(bucket_key)
            if wait > 0:
                logger.info("[%s] Throttling %.1fs for %s", self.name, wait, bucket_key)
                time.sleep(wait)

    def _fetch(
        self,
        url: str,
        method: str = "GET",
        params: dict | None = None,
        context: str = "",
    ) -> httpx.Response | None:
        ctx = context or self.name
        for attempt in range(self._retry_policy.max_retries):
            self._throttle(ctx)
            try:
                resp = self._http.request(method, url, params=params)
                resp.raise_for_status()
                return resp
            except Exception as e:
                classified = classify_error(e, context=ctx)
                decision = self._retry_policy.should_retry(e, attempt)
                if decision.value == "abort":
                    logger.warning("[%s] Abort after %d: %s", ctx, attempt + 1, classified.message)
                    return None
                if attempt < self._retry_policy.max_retries - 1:
                    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (429, 503):
                        ra = e.response.headers.get("Retry-After")
                        retry_after = float(ra) if ra else None
                    else:
                        retry_after = None
                    delay = self._retry_policy.get_delay(attempt, retry_after=retry_after)
                    logger.info("[%s] Retry %d/%d after %.1fs: %s", ctx, attempt + 1, self._retry_policy.max_retries, delay, classified.message)
                    time.sleep(delay)
        return None

    def _fetch_pdf(self, url: str, context: str = "") -> tuple[bytes | None, bool]:
        ctx = context or self.name
        cached = self._cache.get(url) if self._cache else None
        if cached is not None:
            return bytes.fromhex(cached) if cached else None, False

        resp = self._fetch(url, context=ctx)
        if resp is None:
            return None, False

        content = resp.content
        md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()
        if self._cache:
            cached_md5 = self._cache.get_md5(url)
            if cached_md5 == md5:
                logger.info("[%s] Cache hit (MD5 unchanged)", ctx)
                return None, False
            self._cache.set(url, content.hex(), md5=md5, ttl=86400)

        return content, True

    def _fetch_html(self, url: str, params: dict | None = None, context: str = "") -> str | None:
        resp = self._fetch(url, params=params, context=context)
        if resp is None:
            return None
        return resp.text

    def _fetch_json(self, url: str, params: dict | None = None, context: str = "") -> dict | list | None:
        resp = self._fetch(url, params=params, context=context)
        if resp is None:
            return None
        try:
            return resp.json()
        except Exception as e:
            classified = classify_error(e, context=context or url)
            logger.warning("[%s] JSON parse error: %s", self.name, classified.message)
            return None

    def extract_pdf_text(self, pdf_bytes: bytes) -> str:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if row:
                            text_parts.append(" | ".join(str(c) for c in row if c))
        return "\n".join(text_parts)

    @abstractmethod
    def run(self, *args, **kwargs) -> list[dict]: ...
