"""Testes do WebsiteScraper — modo Shopify JSON API e parsing.

Regressao para a correcao raiz do Chefon (2026-07-17): as paginas HTML
/collections/* retornavam HTTP 429 (Cloudflare). A rota publica da Shopify
Storefront API /collections/all/products.json NAO dispara challenge e
retorna JSON estruturado. O scraper deve coletar 100% via JSON.
"""

from scrapers.website_scraper import WebsiteScraper


def _make_product(title, price, vendor="MarcaX", available=True):
    return {
        "title": title,
        "vendor": vendor,
        "variants": [{"price": str(price), "available": available}],
    }


def _fake_http(pages: dict):
    """Monta um objeto _http fake que responde products.json paginado."""

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _Http:
        def __init__(self, pages):
            self._pages = pages

        def get(self, url, params=None):
            page = int((params or {}).get("page", 1))
            return _Resp(self._pages.get(page, {"products": []}))

        def close(self):
            return None

    return _Http(pages)


def _chefon_config():
    return {
        "name": "Chefon",
        "base_url": "https://chefon.com.br",
        "shopify_json": True,
        "shopify_collections": ["all"],
        "shopify_page_limit": 250,
        "shopify_max_pages": 40,
    }


def test_shopify_json_mode_collects_all_pages():
    cfg = _chefon_config()
    # Paginas cheias (== page_limit) forcam a continuacao; a ultima vazia encerra.
    page1 = {"products": [_make_product(f"P1-{i}", float(i)) for i in range(1, 251)]}
    page2 = {"products": [_make_product("Leite Condensado 395g", 9.90), _make_product("Chocolate 1kg", 45.0, "Sicao")]}
    pages = {
        1: page1,
        2: page2,
        3: {"products": []},
    }
    sc = WebsiteScraper(cfg)
    sc._http = _fake_http(pages)
    prods = sc.run([])
    sc.close()
    assert len(prods) == 252
    titles = {p["product"] for p in prods}
    assert "Leite Condensado 395g" in titles
    assert prods[250]["brand"] == "MarcaX"
    assert {"product", "price", "unit", "validity_raw", "brand"} <= set(prods[0].keys())


def test_shopify_json_skips_unavailable_variants_price_kept():
    cfg = _chefon_config()
    pages = {
        1: {
            "products": [
                _make_product("Disponivel 1kg", 10.0, available=True),
                _make_product("Indisponivel 1kg", 99.0, available=False),
            ]
        },
        2: {"products": []},
    }
    sc = WebsiteScraper(cfg)
    sc._http = _fake_http(pages)
    prods = sc.run([])
    sc.close()
    # Ambos tem price > 0; indisponivel cai na primeira variante disponivel,
    # mas aqui nenhuma disponivel -> usa primeira variante qualquer (fallback).
    assert len(prods) == 2


def test_shopify_json_handles_zero_price_and_missing():
    cfg = _chefon_config()
    pages = {
        1: {
            "products": [
                {"title": "Sem preco", "variants": [{"price": None}]},
                {"title": "Preco zero", "variants": [{"price": "0"}]},
                _make_product("Ok 500g", 12.30),
            ]
        },
        2: {"products": []},
    }
    sc = WebsiteScraper(cfg)
    sc._http = _fake_http(pages)
    prods = sc.run([])
    sc.close()
    assert len(prods) == 1
    assert prods[0]["product"] == "Ok 500g"
    assert prods[0]["price"] == 12.30


def test_shopify_json_non_shopify_falls_back_to_browse():
    cfg = dict(_chefon_config())
    cfg["shopify_json"] = False
    cfg["browse_urls"] = ["https://chefon.com.br/collections/all"]
    sc = WebsiteScraper(cfg)
    # Nao deve chamar o ramo shopify; apenas garantir instanciacao ok.
    assert sc.shopify_json is False
    sc.close()


def test_fetch_browse_thread_isolation_timeout_returns_none():
    """Thread isolation: teto de parede estoura e retorna None sem travar."""
    from scrapers.website_scraper import WebsiteScraper

    sc = WebsiteScraper({**_chefon_config(), "browse_url_timeout": 0.05})
    # Stub que trava: se o request rodasse inline travaria o teste.
    sc._fetch_browse_raw = lambda url: _sleep_forever()
    result = sc.fetch_browse("https://chefon.com.br/collections/all")
    assert result is None  # teto estourou, retorna None
    sc.close()


def _sleep_forever():
    import time as _time

    _time.sleep(30)
    return "<html/>"


def test_fetch_browse_returns_content_within_timeout():
    """Sem timeout: retorna o HTML normalmente."""
    from scrapers.website_scraper import WebsiteScraper

    sc = WebsiteScraper({**_chefon_config(), "browse_url_timeout": 5})
    sc._fetch_browse_raw = lambda url: "<html><body>produtos</body></html>"
    result = sc.fetch_browse("https://chefon.com.br/collections/all")
    assert result == "<html><body>produtos</body></html>"
    sc.close()
