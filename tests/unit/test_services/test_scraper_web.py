class TestWebsiteScraper:
    def test_parse_results_with_validity_selector(self):
        """Product_validity selector presente retorna validity_raw."""
        from scrapers.website_scraper import WebsiteScraper

        store = {
            "name": "TestStore",
            "base_url": "https://test.com",
            "selectors": {
                "product_card": [".card"],
                "product_name": [".name"],
                "product_price": [".price"],
                "product_validity": [".validity"],
            },
        }
        scraper = WebsiteScraper(store)

        html = """
        <html><body>
            <div class="card">
                <div class="name">Leite Moca CX 12x395g</div>
                <div class="price">R$ 42,90</div>
                <div class="validity">Valido ate 30/06/2026</div>
            </div>
        </body></html>
        """

        results = scraper.parse_products(html)
        assert len(results) == 1
        assert results[0]["validity_raw"] == "Valido ate 30/06/2026"

    def test_parse_results_no_validity_selector(self):
        """Sem product_validity, validity_raw vazio."""
        from scrapers.website_scraper import WebsiteScraper

        scraper = WebsiteScraper(
            {
                "name": "TestStore",
                "base_url": "https://test.com",
                "selectors": {
                    "product_card": [".card"],
                    "product_name": [".name"],
                    "product_price": [".price"],
                },
            }
        )
        html = """
        <html><body>
            <div class="card">
                <div class="name">Farinha 1kg</div>
                <div class="price">R$ 5,90</div>
            </div>
        </body></html>
        """

        results = scraper.parse_products(html)
        assert len(results) == 1
        assert results[0]["validity_raw"] == ""
