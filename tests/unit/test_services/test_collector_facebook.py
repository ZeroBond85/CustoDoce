"""Test collect_facebook_flyers collector function with mocked dependencies."""

from unittest.mock import MagicMock, patch

import pytest


class TestCollectFacebookFlyers:
    @patch("services.collector.load_stores")
    @patch("services.collector._collect_prices")
    def test_collect_facebook_flyers_filters_and_calls_collect(
        self, mock_collect_prices, mock_load_stores
    ):
        """collect_facebook_flyers filters stores by type+scraper+active and calls _collect_prices."""
        from services.collector import collect_facebook_flyers

        mock_load_stores.return_value = [
            {"name": "FBLoja", "type": "facebook_flyer", "scraper": "facebook_flyer_scraper", "is_active": True},
            {"name": "Other", "type": "website_js", "scraper": "playwright_price_scraper", "is_active": True},
            {"name": "Inactive", "type": "facebook_flyer", "scraper": "facebook_flyer_scraper", "is_active": False},
        ]
        mock_collect_prices.return_value = [{"product": "Leite", "price": 5.0, "unit": "1L"}]

        ingredients = [{"canonical_name": "Leite Condensado", "search_terms": ["leite condensado"]}]
        result = collect_facebook_flyers(ingredients)

        # Should only pass the active facebook_flyer store
        assert mock_collect_prices.call_count == 1
        args, _ = mock_collect_prices.call_args
        passed_stores = args[0]
        assert len(passed_stores) == 1
        assert passed_stores[0]["name"] == "FBLoja"

        # Result should be what _collect_prices returns
        assert result == [{"product": "Leite", "price": 5.0, "unit": "1L"}]

    @patch("services.collector.load_stores")
    def test_collect_facebook_flyers_no_matching_stores(self, mock_load_stores):
        """Returns empty list when no matching stores."""
        from services.collector import collect_facebook_flyers

        mock_load_stores.return_value = [
            {"name": "Other", "type": "website_js", "scraper": "playwright_price_scraper", "is_active": True},
        ]

        result = collect_facebook_flyers([])
        assert result == []


class TestFacebookFlyerScraper:
    """Unit tests for FacebookFlyerScraper with mocked network/OCR."""

    def test_scraper_requires_page_url(self):
        """FacebookFlyerScraper raises if no page_url/base_url provided."""
        from scrapers.facebook_flyer_scraper import FacebookFlyerScraper

        with pytest.raises(ValueError):
            FacebookFlyerScraper({"name": "Test", "type": "facebook_flyer"})

    def test_scraper_init_with_page_url(self):
        """FacebookFlyerScraper initializes correctly with page_url."""
        from scrapers.facebook_flyer_scraper import FacebookFlyerScraper

        scraper = FacebookFlyerScraper({"name": "TestFB", "page_url": "https://facebook.com/test"})
        assert scraper.name == "TestFB"
        assert scraper.page_url == "https://facebook.com/test"

    def test_scraper_init_with_base_url_fallback(self):
        """FacebookFlyerScraper falls back to base_url if page_url not provided."""
        from scrapers.facebook_flyer_scraper import FacebookFlyerScraper

        scraper = FacebookFlyerScraper({"name": "TestFB", "base_url": "https://facebook.com/test"})
        assert scraper.page_url == "https://facebook.com/test"

    @patch("scrapers.facebook_flyer_scraper.ocr_image_bytes")
    @patch("scrapers.facebook_flyer_scraper.extract_lines_from_text")
    @patch("scrapers.facebook_flyer_scraper.parse_flyer_lines")
    @patch("httpx.AsyncClient.get")
    def test_process_post_parses_products_from_image(
        self, mock_get, mock_parse, mock_extract, mock_ocr
    ):
        """_process_post downloads image, OCRs, parses flyer lines."""
        from scrapers.facebook_flyer_scraper import FacebookFlyerScraper

        # Mock OCR pipeline
        mock_ocr.return_value = "raw text from image"
        mock_extract.return_value = ["line 1", "line 2"]
        mock_parse.return_value = [
            {"product": "Leite Condensado 395g", "price": 6.50, "unit": "395g", "validity_raw": "2026-07-15", "brand": "Piracanjuba"},
        ]

        # Mock httpx download — resp = await client.get() returns mock_get.return_value
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content = b"fake_image_bytes"
        mock_get.return_value = mock_resp

        scraper = FacebookFlyerScraper({"name": "TestFB", "page_url": "https://facebook.com/test"})

        import asyncio
        result = asyncio.run(scraper._process_post(
            None,  # page not used in this path
            {"image_url": "https://fbcdn.net/img.jpg", "post_date": "2026-07-10"},
            {"canonical_name": "Leite Condensado"}
        ))

        assert mock_ocr.called
        assert mock_extract.called
        assert mock_parse.called
        assert len(result) == 1
        assert result[0]["product"] == "Leite Condensado 395g"
        assert result[0]["source"] == "facebook_flyer"
        assert result[0]["validity_raw"] == "2026-07-15"

    @patch("scrapers.facebook_flyer_scraper.ocr_image_bytes")
    @patch("httpx.AsyncClient.get")
    def test_process_post_handles_download_failure(self, mock_get, mock_ocr):
        """_process_post returns empty list on download failure."""
        from scrapers.facebook_flyer_scraper import FacebookFlyerScraper

        import httpx
        mock_get.side_effect = httpx.RequestError("Network error")

        scraper = FacebookFlyerScraper({"name": "TestFB", "page_url": "https://facebook.com/test"})

        import asyncio
        result = asyncio.run(scraper._process_post(
            None,
            {"image_url": "https://fbcdn.net/img.jpg", "post_date": "2026-07-10"},
            {"canonical_name": "Leite Condensado"}
        ))

        assert result == []
        assert not mock_ocr.called
