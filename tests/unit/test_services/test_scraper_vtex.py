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
