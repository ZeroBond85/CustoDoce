from unittest.mock import patch


class TestBaseWebScraper:
    """Testes P0 para scrapers/base_web_scraper.py — logica sem rede."""

    def _make_concrete_scraper(self, store_config=None, rate_limit=None):
        """Factory method: cria uma subclasse concreta de BaseWebScraper."""
        from scrapers.base_web_scraper import BaseWebScraper

        class ConcreteScraper(BaseWebScraper):
            def parse_products(self, raw_data) -> list[dict]:
                return [{"parsed": True, "data": raw_data[:50]}] if raw_data else []

        cfg = store_config or {"name": "test", "base_url": "https://test.com", "search_url": "{query}"}
        scraper = ConcreteScraper(cfg, rate_limit=rate_limit)
        return scraper

    def test_constructor_defaults(self):
        scraper = self._make_concrete_scraper()
        assert scraper.name == "test"
        assert scraper.base_url == "https://test.com"
        assert scraper.rate_limit == 1.0
        assert scraper._http is not None

    def test_default_accept_encoding_without_brotli(self):
        """Root fix: o header NUNCA anuncia 'br' (brotli) porque o runtime
        nao tem decoder — caso contrario o httpx retorna bytes ilegiveis.

        Esta eh a causa raiz do bug da BarraDoce e afeta todos os scrapers
        BaseWebScraper. Se brotli for suportado no futuro (brotlicffi nas
        requirements), este teste e o header devem ser atualizados juntos.
        """
        scraper = self._make_concrete_scraper()
        ae = scraper._http.headers.get("Accept-Encoding", "")
        assert "br" not in ae
        assert "gzip" in ae

    def test_constructor_custom_rate_limit(self):
        scraper = self._make_concrete_scraper(rate_limit=0.5)
        assert scraper.rate_limit == 0.5

    def test_constructor_rate_limit_from_config(self):
        scraper = self._make_concrete_scraper(
            {"name": "t", "base_url": "https://t.com", "rate_limit": 2.0, "search_url": "{query}"}
        )
        assert scraper.rate_limit == 2.0

    def test_context_manager(self):
        scraper = self._make_concrete_scraper()
        with scraper as s:
            assert s.name == "test"
        # after exit, client should be closed
        assert scraper._http.is_closed

    def test_close(self):
        scraper = self._make_concrete_scraper()
        scraper.close()
        assert scraper._http.is_closed

    def test_fetch_search_empty_url(self):
        scraper = self._make_concrete_scraper({"name": "t", "base_url": "https://t.com"})
        result = scraper.fetch_search("leite")
        assert result is None

    def test_fetch_search_url_formatting(self):
        scraper = self._make_concrete_scraper(
            {"name": "t", "base_url": "https://t.com", "search_url": "https://t.com/busca?q={query}"}
        )
        formatted = scraper.store["search_url"].format(query="leite+condensado")
        assert "busca?q=leite+condensado" in formatted

    def test_parse_products_abstract(self):
        from scrapers.base_web_scraper import BaseWebScraper

        class MissingImpl(BaseWebScraper):
            pass

        import inspect

        assert inspect.isabstract(MissingImpl)

    def test_run_empty_ingredients(self):
        scraper = self._make_concrete_scraper()
        result = scraper.run([])
        assert result == []

    @patch("scrapers.base_web_scraper.BaseWebScraper._search_and_parse")
    def test_run_iterates_ingredients(self, mock_search):
        mock_search.return_value = [{"product": "test", "price": 10.0}]
        scraper = self._make_concrete_scraper()
        ingredients = [
            {"canonical_name": "Leite", "search_terms": ["leite"]},
            {"canonical_name": "Chocolate", "search_terms": ["chocolate"]},
        ]
        result = scraper.run(ingredients)
        assert len(result) == 2
        assert mock_search.call_count == 2

    def test_throttle_positive(self):
        import time

        scraper = self._make_concrete_scraper(rate_limit=0.01)
        start = time.time()
        scraper._throttle()
        elapsed = time.time() - start
        assert elapsed >= 0.01

    def test_throttle_zero(self):
        import time

        scraper = self._make_concrete_scraper(
            {"name": "t", "base_url": "https://t.com", "search_url": "{query}", "rate_limit": 0}
        )
        start = time.time()
        scraper._throttle()
        elapsed = time.time() - start
        assert elapsed < 1.0  # nao deve dormir mais que 1s com rate_limit=0

    def test_fetch_json_network_error(self):
        import httpx
        from unittest.mock import patch

        scraper = self._make_concrete_scraper()
        with patch("scrapers.base_web_scraper.time.sleep"):
            with patch.object(scraper._http, "get", side_effect=httpx.NetworkError("mock error")):
                result = scraper.fetch_json("https://nonexistent.invalid/api")
                assert result is None

    def test_parse_products_concrete(self):
        scraper = self._make_concrete_scraper()
        result = scraper.parse_products("<html>test</html>")
        assert len(result) == 1
        assert result[0]["parsed"] is True
