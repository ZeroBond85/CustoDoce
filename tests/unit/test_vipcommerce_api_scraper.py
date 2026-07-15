from unittest.mock import MagicMock, patch

import pytest

from scrapers.vipcommerce_api_scraper import VipCommerceApiScraper


@pytest.fixture
def store_config():
    return {
        "name": "Spani Atacadista",
        "base_url": "https://www.spanionline.com.br",
        "vip_domain": "spanionline.com.br",
        "vip_org_id": "67",
        "vip_filial_id": "1",
        "vip_cd_id": "15",
        "vip_login_key": "abc123",
        "vip_max_pages_per_dept": 2,
        "rate_limit": 0,
    }


def _resp(payload):
    r = MagicMock()
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


def test_login_sets_token(store_config):
    scraper = VipCommerceApiScraper(store_config)
    with patch.object(scraper._http, "post", return_value=_resp({"success": True, "data": "JWT"})) as mock_post:
        assert scraper._login() is True
    assert scraper._token == "JWT"
    body = mock_post.call_args.kwargs["json"]
    assert body["domain"] == "spanionline.com.br"
    assert body["key"] == "abc123"


def test_login_missing_config_fails():
    scraper = VipCommerceApiScraper({"name": "X", "base_url": "https://x.com"})
    assert scraper._login() is False


def test_select_departments_filters_by_keyword(store_config):
    scraper = VipCommerceApiScraper(store_config)
    scraper._token = "JWT"
    tree = {
        "data": [
            {"classificacao_mercadologica_id": 4, "descricao": "Biscoitos e chocolates"},
            {"classificacao_mercadologica_id": 3, "descricao": "Bebidas"},
            {"classificacao_mercadologica_id": 12, "descricao": "Mercearia"},
            {"classificacao_mercadologica_id": 14, "descricao": "Perfumaria e higiene"},
        ]
    }
    with patch.object(scraper._http, "get", return_value=_resp(tree)):
        deps = scraper._select_departments()
    ids = {d["id"] for d in deps}
    assert ids == {4, 12}


def test_parse_product_extracts_price_and_unit(store_config):
    scraper = VipCommerceApiScraper(store_config)
    parsed = scraper._parse_product({"descricao": "Leite Condensado Moça 395g", "preco": "7,49"})
    assert parsed["product"] == "Leite Condensado Moça 395g"
    assert parsed["price"] == 7.49
    assert parsed["unit"] == "395g"


def test_parse_product_prefers_offer_price(store_config):
    scraper = VipCommerceApiScraper(store_config)
    parsed = scraper._parse_product(
        {"descricao": "Chocolate 1kg", "preco": "30.00", "em_oferta": True, "oferta": {"preco_oferta": "24.90"}}
    )
    assert parsed["price"] == 24.90


def test_parse_product_skips_zero_price(store_config):
    scraper = VipCommerceApiScraper(store_config)
    assert scraper._parse_product({"descricao": "Produto", "preco": "0"}) is None
    assert scraper._parse_product({"descricao": "", "preco": "5"}) is None


def test_fetch_dept_products_paginates_up_to_cap(store_config):
    scraper = VipCommerceApiScraper(store_config)
    scraper._token = "JWT"
    page_payload = {
        "data": [{"descricao": "Item 1kg", "preco": "10.00"}],
        "paginator": {"total_pages": 10},
    }
    with patch.object(scraper._http, "get", return_value=_resp(page_payload)) as mock_get:
        products = scraper._fetch_dept_products({"id": 4, "descricao": "Chocolates"})
    assert mock_get.call_count == 2
    assert len(products) == 2


def test_run_reports_failure_when_login_fails(store_config):
    scraper = VipCommerceApiScraper(store_config)
    with (
        patch.object(scraper, "_login", return_value=False),
        patch.object(scraper, "report_failure") as mock_fail,
    ):
        assert scraper.run([]) == []
    mock_fail.assert_called_once()


def test_run_success_flow(store_config):
    scraper = VipCommerceApiScraper(store_config)
    with (
        patch.object(scraper, "_login", return_value=True),
        patch.object(scraper, "_select_departments", return_value=[{"id": 4, "descricao": "Chocolates"}]),
        patch.object(scraper, "_fetch_dept_products", return_value=[{"product": "X", "price": 1.0, "unit": "1kg"}]),
        patch.object(scraper, "report_success") as mock_ok,
    ):
        result = scraper.run([])
    assert len(result) == 1
    mock_ok.assert_called_once()
