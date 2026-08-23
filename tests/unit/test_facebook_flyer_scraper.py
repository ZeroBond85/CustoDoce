"""SSRF guard do FacebookFlyerScraper (LESSONS #87 / audit A-03).

A image_url vem do DOM de uma pagina publica do Facebook (conteudo de
terceiros). Garante que:
1. IP privado/metadata nunca gera request (guard_url bloqueia antes).
2. O download passa obrigatoriamente por make_safe_async_client
   (re-validacao de cada hop de redirect).
3. Redirect para IP privado/metadata e bloqueado pelo event hook.
"""

import asyncio

import httpx
import pytest

from scrapers import facebook_flyer_scraper as ffs
from services.url_guard import guard_url, make_safe_async_client

pytestmark = pytest.mark.unit


def _make_scraper() -> ffs.FacebookFlyerScraper:
    return ffs.FacebookFlyerScraper({"name": "TestFB", "page_url": "https://facebook.com/TestFB"})


# ── 1. guard_url puro: metadata/private literal IP ──────────────


def test_guard_blocks_metadata_literal_ip():
    assert guard_url("http://169.254.169.254/latest/meta-data/") is None


def test_guard_blocks_localhost():
    assert guard_url("http://localhost:8501/admin") is None


# ── 2. scraper nao faz request quando guard bloqueia ────────────


def test_download_blocks_private_ip_url(monkeypatch):
    scraper = _make_scraper()

    def _boom(**kwargs):
        raise AssertionError("client NAO deve ser construido para URL bloqueada")

    monkeypatch.setattr(ffs, "make_safe_async_client", _boom)

    post_data = {"image_url": "http://169.254.169.254/latest/meta-data/", "post_date": ""}
    out = asyncio.run(scraper._process_post(page=None, post_data=post_data, ing={}))

    assert out == []


# ── 3. caminho feliz: download via safe client com a URL validada ──


def test_download_uses_safe_async_client(monkeypatch):
    scraper = _make_scraper()
    captured: dict = {}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def get(self, url, **kwargs):
            captured["url"] = str(url)
            return httpx.Response(200, content=b"\x89PNG-fake-image")

    def _factory(**kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return FakeAsyncClient()

    # Offline: identity-guard (comportamento do guard real ja coberto acima).
    monkeypatch.setattr(ffs, "guard_url", lambda u, **k: u)
    monkeypatch.setattr(ffs, "make_safe_async_client", _factory)
    monkeypatch.setattr(ffs, "ocr_image_bytes", lambda b: "")

    target = "https://scontent.fbcdn.net/flyer.jpg"
    post_data = {"image_url": target, "post_date": "2026-08-22"}
    out = asyncio.run(scraper._process_post(page=None, post_data=post_data, ing={}))

    assert out == []  # OCR vazio -> sem produtos, mas download aconteceu
    assert captured["url"] == target
    assert captured["timeout"] == 30.0


# ── 4. redirect para privado/metadata bloqueado pelo hook ───────


def test_make_safe_async_client_blocks_private_redirect():
    def handler(request):
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/x"})

    client = make_safe_async_client(transport=httpx.MockTransport(handler), follow_redirects=True)
    try:
        with pytest.raises(httpx.UnsupportedProtocol, match="SSRF guard"):
            asyncio.run(client.get("https://scontent.fbcdn.net/a.jpg"))
    finally:
        asyncio.run(client.aclose())


def test_make_safe_async_client_allows_clean_redirect(monkeypatch):
    # Offline: DNS real do guard substituido por IP publico fixo (regra #3).
    monkeypatch.setattr(
        "services.url_guard.resolve_public_ips",
        lambda host: ["93.184.216.34"],
    )
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(302, headers={"Location": "https://fbcdn.net/real.jpg"})
        return httpx.Response(200, content=b"ok")

    client = make_safe_async_client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    try:
        resp = asyncio.run(client.get("https://facebook.com/img.jpg"))
    finally:
        asyncio.run(client.aclose())
    assert resp.status_code == 200
    assert resp.content == b"ok"
