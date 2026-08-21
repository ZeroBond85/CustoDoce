from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from scrapers.base_unified import BaseScraper


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Congela time.sleep - retries/backoff reais nao sao alvo destes testes."""
    monkeypatch.setattr("time.sleep", lambda *_: None)


class _ConcreteScraper(BaseScraper):
    def run(self, *args, **kwargs) -> list[dict]:
        return []


@pytest.fixture
def store_config():
    return {
        "name": "Test Store",
        "type": "website_catalog",
        "base_url": "https://test.com",
        "rate_limit": 10,
        "anti_bot": False,
    }


@pytest.fixture
def scraper(store_config):
    with patch("scrapers.base_unified.make_safe_client") as mock_client:
        mock_http = MagicMock(spec=httpx.Client)
        mock_client.return_value = mock_http
        s = _ConcreteScraper(store_config, use_cache=False)
        s._http = mock_http
        yield s


def test_init(scraper):
    assert scraper.name == "Test Store"
    assert scraper.store_name == "Test Store"


def test_init_with_anti_bot():
    cfg = {
        "name": "Anti Bot Store",
        "type": "website_catalog",
        "anti_bot": True,
    }
    with patch("scrapers.base_unified.make_safe_client"):
        s = _ConcreteScraper(cfg, use_cache=False)
    assert s.name == "Anti Bot Store"


def test_store_name_property(scraper):
    assert scraper.store_name == "Test Store"


def test_report_failure(scraper):
    with patch("services.scraper_health.record_failure") as mock_rf:
        result = scraper.report_failure("test error", items_found=5)
        mock_rf.assert_called_once()
        assert result == mock_rf.return_value


def test_report_success(scraper):
    with patch("services.scraper_health.record_success") as mock_rs:
        result = scraper.report_success(items_found=10, products_matched=5)
        mock_rs.assert_called_once()
        assert result == mock_rs.return_value


def test_run_abstract():
    with pytest.raises(TypeError):
        BaseScraper({"name": "x", "type": "x"})  # type: ignore[abstract]


def test_throttle(scraper):
    scraper._throttle("test_key")


def test_fetch_success(scraper):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    scraper._http.request.return_value = mock_resp

    resp = scraper._fetch("https://test.com/api")
    assert resp is mock_resp


def test_fetch_404_aborts(scraper):
    request = httpx.Request("GET", "https://test.com/api")
    response = httpx.Response(404, request=request)
    exc = httpx.HTTPStatusError("404", request=request, response=response)
    scraper._http.request.side_effect = exc

    resp = scraper._fetch("https://test.com/api")
    assert resp is None


def test_fetch_timeout_retries(scraper):
    scraper._retry_policy.max_retries = 2
    scraper._http.request.side_effect = httpx.TimeoutException("timeout")

    resp = scraper._fetch("https://test.com/api")
    assert resp is None
    assert scraper._http.request.call_count == 2


def test_fetch_json_success(scraper):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"key": "value"}
    scraper._http.request.return_value = mock_resp

    result = scraper._fetch_json("https://test.com/api.json")
    assert result == {"key": "value"}


def test_fetch_html_success(scraper):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.text = "<html><body>test</body></html>"
    scraper._http.request.return_value = mock_resp

    result = scraper._fetch_html("https://test.com/page")
    assert result == "<html><body>test</body></html>"


def test_extract_pdf_text(scraper):
    pdf_bytes = _make_minimal_pdf()
    text = scraper.extract_pdf_text(pdf_bytes)
    assert isinstance(text, str)


def test_close(scraper):
    with patch.object(scraper._http, "close") as mock_close:
        scraper.close()
        mock_close.assert_called_once()


def test_context_manager(scraper):
    with patch.object(scraper._http, "close") as mock_close:
        with scraper as s:
            assert s is scraper
        mock_close.assert_called_once()


def _make_minimal_pdf() -> bytes:
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td"
        b"(Hello World) Tj ET\nendstream\nendobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000058 00000 n \n0000000115 00000 n \n0000000266 00000 n \n"
        b"0000000365 00000 n \ntrailer<</Size 6/Root 1 0 R>>\nstartxref\n437\n%%EOF"
    )
