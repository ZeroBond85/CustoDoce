"""Testes unitários do RoldaoApiScraper.

Cobre o hardening (Sprint 20): timeout configurável via `http_timeout` da
loja, retry/backoff em falhas de rede (em vez de engolir e abortar o encarte),
e o residual inesperado retornando None sem warning.
"""

from unittest.mock import MagicMock, patch

import httpx

from scrapers.roldao_api_scraper import RoldaoApiScraper


def _make_scraper(config: dict | None = None) -> RoldaoApiScraper:
    base = {
        "name": "Roldão Atacadista",
        "api_base": "https://blog.roldao.com.br/wp-json/wp/v2",
        "api_endpoints": {"media": "/media/{media_id}"},
    }
    if config:
        base.update(config)
    scraper = RoldaoApiScraper(base)
    scraper._http = MagicMock()
    return scraper


def test_uses_http_timeout_from_config():
    """O timeout configurado (http_timeout) deve ser repassado ao _http.get."""
    scraper = _make_scraper({"http_timeout": {"connect": 15.0, "read": 30.0}})
    scraper._http.get.return_value = MagicMock(
        status_code=200,
        raise_for_status=lambda: None,
        json=lambda: {"guid": {"rendered": "x"}},
    )

    scraper.get_media(42)

    scraper._http.get.assert_called_once()
    kwargs = scraper._http.get.call_args.kwargs
    assert "timeout" in kwargs
    assert kwargs["timeout"].connect == 15.0
    assert kwargs["timeout"].read == 30.0


def test_network_error_retries_with_backoff():
    """Timeout/NetworkError relança p/ o @_retry_with_backoff (3 tentativas)."""
    scraper = _make_scraper()
    scraper._http.get.side_effect = httpx.NetworkError("Connection reset by peer")

    with patch("scrapers.base_web_scraper.time.sleep", return_value=None) as sleep:
        result = scraper.get_media(7)

    assert result is None  # decorator esgota e retorna None
    assert scraper._http.get.call_count == 4  # tentativa inicial + 3 retries
    assert sleep.call_count >= 3


def test_unexpected_error_returns_none_without_warning():
    """Erro inesperado (não-rede, ex.: JSON) retorna None e NÃO loga warning."""
    scraper = _make_scraper()
    scraper._http.get.return_value = MagicMock(
        status_code=200,
        raise_for_status=lambda: None,
        json=lambda: (_ for _ in ()).throw(ValueError("bad json")),
    )

    with patch("scrapers.roldao_api_scraper.logger.info") as info, patch(
        "scrapers.roldao_api_scraper.logger.warning"
    ) as warn:
        result = scraper.get_media(9)

    assert result is None
    info.assert_called()
    warn.assert_not_called()


def test_http_status_error_retries_with_backoff():
    """HTTPStatusError (5xx) relança p/ o decorator respeitar Retry-After."""
    scraper = _make_scraper()

    resp = MagicMock()
    resp.status_code = 503
    resp.headers.get.return_value = None
    err = httpx.HTTPStatusError("503", request=MagicMock(), response=resp)
    scraper._http.get.side_effect = err

    with patch("scrapers.base_web_scraper.time.sleep", return_value=None):
        result = scraper.get_media(11)

    assert result is None  # decorator esgota e retorna None
    assert scraper._http.get.call_count == 4
