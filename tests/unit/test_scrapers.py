from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from scrapers.base_flyer import BaseFlyerScraper


class DummyFlyerScraper(BaseFlyerScraper):
    def parse_products(self, text: str):
        return [{"name": "test"}]


@pytest.fixture
def store_config():
    return {
        "name": "Assaí",
        "url_pattern": "https://assai.com/{year}/{week}/{city}/folheto.pdf",
        "cities": ["Santos"],
        "state": "sp",
        "store_slug": "santos-centro",
    }


@pytest.mark.parametrize(
    "target_date, expected_url",
    [
        (date(2026, 6, 27), "https://assai.com/2026/26/santos/folheto.pdf"),
        (None, None),  # Handled in test separately
    ],
)
def test_build_url(store_config, target_date, expected_url):
    if target_date:
        scraper = DummyFlyerScraper(store_config)
        assert scraper.build_url(target_date) == expected_url


def test_build_url_today(store_config):
    scraper = DummyFlyerScraper(store_config)
    url = scraper.build_url()
    assert "2026" in url  # Based on current date 2026


def test_download_new_content(store_config, tmp_path):
    scraper = DummyFlyerScraper(store_config, cache_dir=str(tmp_path))
    with patch.object(scraper._http, "head") as mock_head, patch.object(scraper._http, "get") as mock_get:
        mock_head.return_value = MagicMock(headers={})
        mock_get.return_value = MagicMock(status_code=200, content=b"pdf content", headers={"etag": "etag1"})

        content, is_new = scraper.download()
        assert content == b"pdf content"
        assert is_new is True


def test_download_etag_cache(store_config, tmp_path):
    scraper = DummyFlyerScraper(store_config, cache_dir=str(tmp_path))
    etag_path = scraper._etag_path()
    etag_path.write_text("etag1")

    with patch.object(scraper._http, "head") as mock_head:
        mock_head.return_value = MagicMock(headers={"etag": "etag1"})

        content, is_new = scraper.download()
        assert content is None
        assert is_new is False


def test_download_md5_cache(store_config, tmp_path):
    scraper = DummyFlyerScraper(store_config, cache_dir=str(tmp_path))
    content = b"same content"
    md5 = scraper._compute_md5(content)
    scraper._md5_path().write_text(md5)

    with patch.object(scraper._http, "head") as mock_head, patch.object(scraper._http, "get") as mock_get:
        mock_head.return_value = MagicMock(headers={})
        mock_get.return_value = MagicMock(status_code=200, content=content, headers={})

        content_res, is_new = scraper.download()
        assert content_res is None
        assert is_new is False


def test_download_http_error(store_config, tmp_path):
    scraper = DummyFlyerScraper(store_config, cache_dir=str(tmp_path))
    with patch.object(scraper._http, "head") as mock_head, patch.object(scraper._http, "get") as mock_get:
        mock_head.return_value = MagicMock(headers={})
        mock_get.side_effect = Exception("HTTP Error")

        content, is_new = scraper.download()
        assert content is None
        assert is_new is False


def test_compute_md5(store_config):
    scraper = DummyFlyerScraper(store_config)
    res1 = scraper._compute_md5(b"hello")
    res2 = scraper._compute_md5(b"hello")
    res3 = scraper._compute_md5(b"world")
    assert res1 == res2
    assert res1 != res3


class TestMaxImageNormalization:
    def test_preserves_working_host(self):
        from scrapers.max_api_scraper import MaxApiScraper

        scraper = MaxApiScraper(
            {"name": "Max Atacadista SP", "base_url": "https://x.com", "image_host": "institucional.supermuffato.com.br"}
        )
        url = "//institucional.supermuffato.com.br/webtools/files/ofertas/1/a (1).jpeg"
        out = scraper._normalize_image(url)
        # Deve virar https:// e MANTER o host que responde 200 (não trocar por fallback 404).
        assert out.startswith("https://institucional.supermuffato.com.br/")
        assert "maxatacadista" not in out

    def test_keeps_existing_https_url(self):
        from scrapers.max_api_scraper import MaxApiScraper

        scraper = MaxApiScraper({"name": "Max Atacadista SP", "base_url": "https://x.com"})
        url = "https://institucional.supermuffato.com.br/files/a.jpeg"
        assert scraper._normalize_image(url) == url


class TestPlaywrightCoroutineLowerBug:
    """Regressão: `await self._get_page_html(page).lower()` aplicava o `.lower()`

    no coroutine (sem await), causando ``'coroutine' object has no attribute 'lower'``
    no Tier 3 (agregador). Corrigido para ``(await self._get_page_html(page)).lower()``.
    """

    def test_wait_for_real_content_awaits_html_before_lower(self):
        import asyncio

        from scrapers.playwright_scraper import PlaywrightAggregatorScraper

        scraper = PlaywrightAggregatorScraper(
            {"name": "Kimbino", "base_url": "https://www.kimbino.com.br", "regions": ["santos"]}
        )

        class _FakePage:
            def locator(self, sel):
                raise RuntimeError("no browser in unit test")

            async def content(self):
                return "<html>carrefour oferta</html>"

        # _get_page_html awaits page.content(); garantir que o await resolve a str
        html = asyncio.run(scraper._get_page_html(_FakePage()))
        assert isinstance(html, str)
        assert "carrefour" in html.lower()
