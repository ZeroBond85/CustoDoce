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
