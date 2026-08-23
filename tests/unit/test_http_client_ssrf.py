"""Unit tests para PR-06 — SSRF guard no http_client.py compartilhado."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from services.http_client import get_client, get_async_client
from services.url_guard import guard_url


def test_sync_client_has_response_hook():
    client = get_client()
    assert client.event_hooks["response"]


@pytest.mark.asyncio
async def test_async_client_has_response_hook():
    client = get_async_client()
    assert client.event_hooks["response"]
    await client.aclose()


def test_guard_blocks_cross_site_redirect():
    """Same-site hop permitido, cross-site bloqueado (via url_guard)."""

    # Same-site: apex -> www (permite sem DNS)
    assert guard_url("https://barradoce.com.br") is None  # não allowlisted → bloqueado
    assert guard_url("https://www.barradoce.com.br") is None

    # Host com palavra-chave bloqueada (metadata, localhost, etc.) → None
    assert guard_url("http://metadata.internal/") is None
    assert guard_url("http://169.254.169.254/") is None

    # allowlisted + https passa
    assert guard_url("https://supabase.co") is not None
