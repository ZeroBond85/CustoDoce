"""
services/http_client.py

Shared httpx client with connection pooling, retry with backoff,
and configurable timeouts. Reuse across all scrapers, LLM calls,
and external API requests.

Usage:
    client = get_client()
    r = client.get("https://...")
    r = client.post("https://...", json={...})

For async:
    async with get_async_client() as client:
        r = await client.get("https://...")
"""

from __future__ import annotations

import os
import secrets
import time

import httpx

_DEFAULT_TIMEOUT = float(os.environ.get("HTTP_CLIENT_TIMEOUT", "30"))
_DEFAULT_MAX_RETRIES = int(os.environ.get("HTTP_CLIENT_MAX_RETRIES", "3"))
_DEFAULT_POOL_SIZE = int(os.environ.get("HTTP_CLIENT_POOL_SIZE", "50"))
_DEFAULT_RETRY_BACKOFF = float(os.environ.get("HTTP_CLIENT_BACKOFF", "1.0"))

_client: httpx.Client | None = None
_async_client: httpx.AsyncClient | None = None


def _make_limits() -> httpx.Limits:
    return httpx.Limits(
        max_keepalive_connections=_DEFAULT_POOL_SIZE,
        max_connections=_DEFAULT_POOL_SIZE,
        keepalive_expiry=60.0,
    )


def get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            timeout=httpx.Timeout(_DEFAULT_TIMEOUT),
            limits=_make_limits(),
            follow_redirects=True,
        )
    return _client


def get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None:
        _async_client = httpx.AsyncClient(
            timeout=httpx.Timeout(_DEFAULT_TIMEOUT),
            limits=_make_limits(),
            follow_redirects=True,
        )
    return _async_client


def close_clients():
    global _client, _async_client
    if _client is not None:
        _client.close()
        _client = None
    if _async_client is not None:
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            _async_client.aclose()
            _async_client = None


def retry_with_backoff(
    url: str,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    base_delay: float = _DEFAULT_RETRY_BACKOFF,
    **kwargs,
) -> httpx.Response:
    """GET with exponential backoff retry. Uses shared client."""
    client = get_client()
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            r = client.get(url, **kwargs)
            if r.status_code < 500:
                return r
            last_exc = httpx.HTTPStatusError(
                f"HTTP {r.status_code}", request=r.request, response=r
            )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as e:
            last_exc = e
        if attempt < max_retries:
            delay = min(base_delay * (2**attempt) + secrets.randbelow(500) / 1000, 30.0)
            time.sleep(delay)
    raise last_exc


async def retry_with_backoff_async(
    url: str,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    base_delay: float = _DEFAULT_RETRY_BACKOFF,
    **kwargs,
) -> httpx.Response:
    """Async GET with exponential backoff retry."""
    import asyncio

    client = get_async_client()
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            r = await client.get(url, **kwargs)
            if r.status_code < 500:
                return r
            last_exc = httpx.HTTPStatusError(
                f"HTTP {r.status_code}", request=r.request, response=r
            )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as e:
            last_exc = e
        if attempt < max_retries:
            delay = min(base_delay * (2**attempt) + secrets.randbelow(500) / 1000, 30.0)
            await asyncio.sleep(delay)
    raise last_exc
