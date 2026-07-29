"""Testes do CarrefourGraphQLScraper — migração de HTML (403) para GraphQL API."""

from scrapers.carrefour_graphql_scraper import CarrefourGraphQLScraper


def _make_graphql_response(products):
    """Monta resposta GraphQL com produtos."""
    edges = [{"node": p} for p in products]
    return {"data": {"search": {"products": {"edges": edges, "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}


def _chefon_config():
    return {
        "name": "Carrefour Mercado",
        "base_url": "https://mercado.carrefour.com.br",
        "type": "website_catalog",
        "scraper": "carrefour_graphql_scraper",
        "graphql_endpoint": "https://mercado.carrefour.com.br/_v/segment/graphql/v1",
        "headers_custom": {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
        "persist_cookies": True,
        "graphql_variables_template": {"term": "{query}", "first": 50, "after": None},
    }


def _mock_http_response(products):
    """Mock do httpx response para GraphQL."""

    class _Resp:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    return _Resp(products)


def test_graphql_parse_basic_product():
    cfg = _chefon_config()
    sc = CarrefourGraphQLScraper(cfg)
    sc.close()

    products = [
        {
            "id": "1",
            "name": "Leite Condensado 395g",
            "priceRange": {"minVariantPrice": {"amount": "9.90", "currency": "BRL"}},
            "brand": {"name": "Moça"},
            "description": "Leite condensado sachê 395g",
        },
    ]
    resp = _make_graphql_response(products)
    entries = sc._parse_graphql_response(resp, "leite condensado")
    assert len(entries) == 1
    assert entries[0]["product"] == "Leite Condensado 395g"
    assert entries[0]["price"] == 9.90
    assert entries[0]["brand"] == "Moça"


def test_graphql_skip_zero_price():
    cfg = _chefon_config()
    sc = CarrefourGraphQLScraper(cfg)
    sc.close()

    products = [
        {"id": "1", "name": "Sem preco", "priceRange": {"minVariantPrice": {"amount": None}}},
        {"id": "2", "name": "Preco zero", "priceRange": {"minVariantPrice": {"amount": "0"}}},
        {"id": "3", "name": "Ok 500g", "priceRange": {"minVariantPrice": {"amount": "12.30"}}},
    ]
    resp = _make_graphql_response(products)
    entries = sc._parse_graphql_response(resp, "test")
    assert len(entries) == 1
    assert entries[0]["product"] == "Ok 500g"
    assert entries[0]["price"] == 12.30


def test_graphql_skip_missing_name():
    cfg = _chefon_config()
    sc = CarrefourGraphQLScraper(cfg)
    sc.close()

    products = [
        {"id": "1", "name": "", "priceRange": {"minVariantPrice": {"amount": "10.00"}}},
        {"id": "2", "name": "Produto Valido", "priceRange": {"minVariantPrice": {"amount": "15.00"}}},
    ]
    resp = _make_graphql_response(products)
    entries = sc._parse_graphql_response(resp, "test")
    assert len(entries) == 1
    assert entries[0]["product"] == "Produto Valido"


def test_graphql_variables_format():
    cfg = _chefon_config()
    sc = CarrefourGraphQLScraper(cfg)
    sc.close()

    vars = sc._get_variables("leite condensado")
    assert vars["term"] == "leite%20condensado"
    assert vars["first"] == 50


def test_graphql_safe_in_parent():
    cfg = _chefon_config()
    sc = CarrefourGraphQLScraper(cfg)
    sc.close()
    assert sc.safe_in_parent is True


def test_graphql_parse_empty_response():
    cfg = _chefon_config()
    sc = CarrefourGraphQLScraper(cfg)
    sc.close()

    resp = {"data": {"search": {"products": {"edges": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}
    entries = sc._parse_graphql_response(resp, "test")
    assert len(entries) == 0


def test_graphql_parse_malformed_response():
    cfg = _chefon_config()
    sc = CarrefourGraphQLScraper(cfg)
    sc.close()

    resp = {"data": {}}
    entries = sc._parse_graphql_response(resp, "test")
    assert len(entries) == 0


def test_graphql_parse_high_price_filtered():
    cfg = _chefon_config()
    sc = CarrefourGraphQLScraper(cfg)
    sc.close()

    products = [
        {"id": "1", "name": "Caro", "priceRange": {"minVariantPrice": {"amount": "15000"}}},
        {"id": "2", "name": "Barato", "priceRange": {"minVariantPrice": {"amount": "9.99"}}},
    ]
    resp = _make_graphql_response(products)
    entries = sc._parse_graphql_response(resp, "test")
    assert len(entries) == 1
    assert entries[0]["product"] == "Barato"


def test_graphql_run_with_mocked_search():
    cfg = _chefon_config()
    sc = CarrefourGraphQLScraper(cfg)

    # Mock _graphql_search to return parsed entries
    def mock_search(query):
        return [
            {"product": "Leite Condensado 395g", "price": 9.90, "unit": "kg", "validity_raw": "", "brand": "Moça"},
        ]

    sc._graphql_search = mock_search
    ingredients = [{"canonical_name": "Leite Condensado", "search_terms": [], "aliases": []}]
    entries = sc.run(ingredients)
    sc.close()

    assert len(entries) == 1
    assert entries[0]["product"] == "Leite Condensado 395g"
    assert entries[0]["price"] == 9.90