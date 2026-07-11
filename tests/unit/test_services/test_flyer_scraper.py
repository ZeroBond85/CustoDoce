class TestPaoFlyerScraper:
    def test_brand_and_campaign_type_overridden(self):
        """PaoFlyerScraper herda de ExtraFlyerScraper e sobrescreve BRAND e CAMPAIGN_TYPE."""
        from scrapers.pao_flyer_scraper import PaoFlyerScraper

        assert PaoFlyerScraper.BRAND == "pao"
        assert PaoFlyerScraper.CAMPAIGN_TYPE == "pao-de-acucar"

    def test_extra_flyer_scraper_defaults(self):
        """ExtraFlyerScraper mantem BRAND e CAMPAIGN_TYPE originais."""
        from scrapers.extra_flyer_scraper import ExtraFlyerScraper

        assert ExtraFlyerScraper.BRAND == "extra"
        assert ExtraFlyerScraper.CAMPAIGN_TYPE == "mercado"

    def test_clean_product_text_rejects_stop_words(self):
        """Herda metodos de limpeza do ExtraFlyerScraper."""
        from scrapers.pao_flyer_scraper import PaoFlyerScraper

        scraper = PaoFlyerScraper({"name": "TestPao"})
        with scraper:
            assert not scraper._is_valid_product("cliente exclusivo oferta")
            assert scraper._is_valid_product("Leite Condensado Moca 395g")
