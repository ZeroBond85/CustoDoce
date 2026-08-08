class TestVtexScraper:
    def test_parse_product_with_validity(self):
        """priceValidUntil extraido do commertialOffer."""
        from scrapers.vtex_scraper import VtexScraper

        scraper = VtexScraper({"name": "TestStore", "base_url": "https://test.com"})
        product = {
            "productName": "Leite Moca",
            "items": [
                {
                    "nameComplete": "Leite Moca CX 12x395g",
                    "sellers": [
                        {
                            "commertialOffer": {
                                "Price": 42.90,
                                "AvailableQuantity": 10,
                                "priceValidUntil": "2026-07-15T23:59:59Z",
                            }
                        }
                    ],
                }
            ],
        }

        entries = scraper.parse_product(product, {"canonical_name": "Leite Moca", "brands": ["Moca"]})
        assert len(entries) == 1
        assert entries[0]["validity_raw"] == "2026-07-15T23:59:59Z"

    def test_parse_product_no_validity(self):
        """Sem priceValidUntil, validity_raw vazio."""
        from scrapers.vtex_scraper import VtexScraper

        scraper = VtexScraper({"name": "TestStore", "base_url": "https://test.com"})
        product = {
            "productName": "Farinha",
            "items": [
                {
                    "nameComplete": "Farinha de Trigo 1kg",
                    "sellers": [
                        {
                            "commertialOffer": {
                                "Price": 5.90,
                                "AvailableQuantity": 5,
                            }
                        }
                    ],
                }
            ],
        }

        entries = scraper.parse_product(product, {"canonical_name": "Farinha", "brands": []})
        assert len(entries) == 1
        assert entries[0]["validity_raw"] == ""

    def test_parse_product_empty_price_valid_until(self):
        """priceValidUntil vazio string."""
        from scrapers.vtex_scraper import VtexScraper

        scraper = VtexScraper({"name": "TestStore", "base_url": "https://test.com"})
        product = {
            "productName": "Acucar",
            "items": [
                {
                    "nameComplete": "Acucar 5kg",
                    "sellers": [
                        {
                            "commertialOffer": {
                                "Price": 18.90,
                                "AvailableQuantity": 3,
                                "priceValidUntil": "",
                            }
                        }
                    ],
                }
            ],
        }

        entries = scraper.parse_product(product, {"canonical_name": "Acucar", "brands": []})
        assert len(entries) == 1
        assert entries[0]["validity_raw"] == ""

    def test_fetch_products_early_exit_on_max_results(self):
        """Early-exit: para de paginar ao atingir vtex_max_results."""
        from scrapers.vtex_scraper import VtexScraper

        scraper = VtexScraper({"name": "TestStore", "base_url": "https://test.com", "vtex_max_results": 75})

        class _Resp:
            def __init__(self, data):
                self._data = data

            def raise_for_status(self):
                return None

            def json(self):
                return self._data

        requested_pages: list[int] = []

        class _Http:
            def get(self, url, params=None):
                requested_pages.append(params["page"])
                # 50 itens por pagina (== page_size), força paginar
                return _Resp([{"productName": f"P{params['page']}-{i}"} for i in range(50)])

        scraper._http = _Http()
        results = scraper._fetch_products("leite", page_size=50)
        assert len(results) == 100  # 2 páginas: 50 + 50 >= 75
        assert requested_pages == [1, 2]
        assert len(requested_pages) < 10  # não paginou tudo

    def test_fetch_products_no_early_exit_without_config(self):
        """Sem vtex_max_results (default 0), paginacao so para em pagina vazia."""
        from scrapers.vtex_scraper import VtexScraper

        scraper = VtexScraper({"name": "TestStore", "base_url": "https://test.com"})

        class _Resp:
            def __init__(self, data):
                self._data = data

            def raise_for_status(self):
                return None

            def json(self):
                return self._data

        requested_pages: list[int] = []

        class _Http:
            def get(self, url, params=None):
                requested_pages.append(params["page"])
                if params["page"] == 2:
                    return _Resp([])  # fim do catalogo
                return _Resp([{"productName": f"P{i}"} for i in range(50)])

        scraper._http = _Http()
        results = scraper._fetch_products("leite", page_size=50)
        assert len(results) == 50
        assert requested_pages == [1, 2]
