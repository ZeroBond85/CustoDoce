"""Test _run_ssr_scraper fallback logic (curl_cffi first, Playwright fallback)."""

from contextlib import ExitStack
from unittest.mock import patch


class TestRunSsrScraper:
    STORE = {"name": "Tiendeo", "base_url": "https://www.tiendeo.com.br"}

    def _run_with_scrapers(self, curl_flyers, pw_flyers, curl_raises=None):
        """Run _run_ssr_scraper with both scraper classes patched."""
        from services.collector import _run_ssr_scraper

        with ExitStack() as stack:
            m_curl = stack.enter_context(patch("scrapers.aggregator_scraper.TiendeoScraper"))
            m_pw = stack.enter_context(patch("scrapers.aggregator_scraper.TiendeoPlaywrightScraper"))

            if curl_raises:
                m_curl.return_value.run.side_effect = curl_raises
            else:
                m_curl.return_value.run.return_value = curl_flyers
            m_pw.return_value.run.return_value = pw_flyers

            result = _run_ssr_scraper(self.STORE)

            return result, m_curl, m_pw

    def test_uses_curl_cffi_when_flyers_returned(self):
        flyers = [{"store_name": "Assaí", "flyer_url": "http://x/1", "source": "tiendeo"}]

        result, m_curl, m_pw = self._run_with_scrapers(curl_flyers=flyers, pw_flyers=[])

        assert result == flyers
        m_curl.return_value.run.assert_called_once()
        m_pw.assert_not_called()

    def test_falls_back_to_playwright_on_zero_flyers(self):
        pw_flyers = [{"store_name": "Extra", "flyer_url": "http://x/2", "source": "tiendeo"}]

        result, m_curl, m_pw = self._run_with_scrapers(curl_flyers=[], pw_flyers=pw_flyers)

        assert result == pw_flyers
        m_curl.return_value.run.assert_called_once()
        m_pw.return_value.run.assert_called_once()

    def test_falls_back_to_playwright_on_exception(self):
        pw_flyers = [{"store_name": "Carrefour", "flyer_url": "http://x/3", "source": "tiendeo"}]

        result, m_curl, m_pw = self._run_with_scrapers(
            curl_flyers=[], pw_flyers=pw_flyers, curl_raises=RuntimeError("Cloudflare 403")
        )

        assert result == pw_flyers
        m_curl.return_value.run.assert_called_once()
        m_pw.return_value.run.assert_called_once()

    def test_returns_empty_when_both_fail(self):
        result, m_curl, m_pw = self._run_with_scrapers(curl_flyers=[], pw_flyers=[])

        assert result == []
        m_curl.return_value.run.assert_called_once()
        m_pw.return_value.run.assert_called_once()
