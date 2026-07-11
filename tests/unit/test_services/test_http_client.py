"""Tests for services/http_client.py: shared pooled httpx client + retry.

Uses httpx.MockTransport so no real network is touched.
"""

import asyncio
from unittest.mock import patch

import httpx
import pytest

from services import http_client


def _sync_mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


# ── get_client singleton + config ────────────────────────────────


def test_get_client_returns_httpx_client():
    c = http_client.get_client()
    try:
        assert isinstance(c, httpx.Client)
    finally:
        http_client.close_clients()


def test_get_client_is_singleton():
    a = http_client.get_client()
    b = http_client.get_client()
    assert a is b
    http_client.close_clients()


def test_client_has_configured_timeout():
    c = http_client.get_client()
    try:
        assert c.timeout.read == http_client._DEFAULT_TIMEOUT
    finally:
        http_client.close_clients()


def test_make_limits_uses_configured_pool_size(monkeypatch):
    monkeypatch.setattr(http_client, "_DEFAULT_POOL_SIZE", 7)
    limits = http_client._make_limits()
    assert limits.max_connections == 7
    assert limits.max_keepalive_connections == 7
    assert limits.keepalive_expiry == 60.0


def test_make_limits_default_pool_size():
    limits = http_client._make_limits()
    assert limits.max_connections == http_client._DEFAULT_POOL_SIZE


# ── close_clients resets singletons ──────────────────────────────


def test_close_clients_resets_sync_singleton():
    c = http_client.get_client()
    assert http_client._client is c
    http_client.close_clients()
    assert http_client._client is None


def test_close_clients_resets_async_singleton_when_no_loop():
    a = http_client.get_async_client()
    assert http_client._async_client is a
    http_client.close_clients()
    assert http_client._async_client is None


# ── retry_with_backoff (sync) ───────────────────────────────────


def test_retry_returns_on_200():
    def handler(request):
        return httpx.Response(200, json={"ok": True})

    with patch.object(http_client, "get_client", return_value=_sync_mock_client(handler)):
        r = http_client.retry_with_backoff("https://example.com")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_retry_backoff_on_500_then_success():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] == 1 else httpx.Response(200)

    with patch.object(http_client, "get_client", return_value=_sync_mock_client(handler)):
        r = http_client.retry_with_backoff("https://x", max_retries=3, base_delay=0)
    assert r.status_code == 200
    assert calls["n"] == 2


def test_retry_backoff_exhausts_on_persistent_500():
    def handler(request):
        return httpx.Response(500)

    with patch.object(http_client, "get_client", return_value=_sync_mock_client(handler)):
        with pytest.raises(httpx.HTTPStatusError):
            http_client.retry_with_backoff("https://x", max_retries=2, base_delay=0)


def test_retry_backoff_on_connect_error_then_success():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200)

    with patch.object(http_client, "get_client", return_value=_sync_mock_client(handler)):
        r = http_client.retry_with_backoff("https://x", max_retries=3, base_delay=0)
    assert r.status_code == 200
    assert calls["n"] == 2


def test_retry_backoff_returns_4xx_without_retry():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404)

    with patch.object(http_client, "get_client", return_value=_sync_mock_client(handler)):
        r = http_client.retry_with_backoff("https://x", max_retries=3, base_delay=0)
    assert r.status_code == 404
    assert calls["n"] == 1


def test_retry_forwards_kwargs():
    seen = {}

    def handler(request):
        seen["params"] = request.url.params.get("q")
        return httpx.Response(200)

    with patch.object(http_client, "get_client", return_value=_sync_mock_client(handler)):
        http_client.retry_with_backoff("https://x", params={"q": "leite"})
    assert seen["params"] == "leite"


# ── retry_with_backoff_async ────────────────────────────────────


def test_retry_async_returns_on_200():
    async def handler(request):
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with patch.object(http_client, "get_async_client", return_value=client):
        r = asyncio.run(http_client.retry_with_backoff_async("https://x"))
    assert r.status_code == 200
    asyncio.run(client.aclose())


def test_retry_async_exhausts_on_500():
    async def handler(request):
        return httpx.Response(500)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with patch.object(http_client, "get_async_client", return_value=client):
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(http_client.retry_with_backoff_async("https://x", max_retries=2, base_delay=0))
    asyncio.run(client.aclose())


def test_retry_async_backoff_on_500_then_success():
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] == 1 else httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with patch.object(http_client, "get_async_client", return_value=client):
        r = asyncio.run(http_client.retry_with_backoff_async("https://x", max_retries=3, base_delay=0))
    assert r.status_code == 200
    assert calls["n"] == 2
    asyncio.run(client.aclose())
