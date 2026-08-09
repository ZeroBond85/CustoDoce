"""Tests for extra/pao flyer scrapers - regression tests for 21f7155."""

from __future__ import annotations

from unittest.mock import patch

from scrapers.extra_flyer_scraper import ExtraFlyerScraper
from scrapers.pao_flyer_scraper import PaoFlyerScraper


class TestExtraFlyerScraperStatics:
    def test_ddmmyyyy_to_yyyymmdd(self):
        assert ExtraFlyerScraper._ddmmyyyy_to_yyyymmdd("10072026") == "20260710"
        assert ExtraFlyerScraper._ddmmyyyy_to_yyyymmdd("01012024") == "20240101"
        assert ExtraFlyerScraper._ddmmyyyy_to_yyyymmdd("invalid") == "invalid"

    def test_is_valid_product(self):
        assert ExtraFlyerScraper._is_valid_product("Leite Condensado Moça 395g") is True
        assert ExtraFlyerScraper._is_valid_product("abc") is False
        assert ExtraFlyerScraper._is_valid_product("caixa total materno") is False
        assert ExtraFlyerScraper._is_valid_product("minuto") is True

    def test_campaign_type_is_mercado(self):
        assert ExtraFlyerScraper.CAMPAIGN_TYPE == "mercado"

    def test_brand_is_extra(self):
        assert ExtraFlyerScraper.BRAND == "extra"


class TestExtraFlyerScraperCampaignLinks:
    def _make_instance(self):
        return ExtraFlyerScraper({"name": "Extra", "base_url": "http://x"})

    def test_prefers_mercado_campaign(self):
        s = self._make_instance()
        data = {
            "extra": {
                "10072026": {
                    "mercado": {"Santos": [{"link": "http://mercado", "codigo_campanha": "1"}]},
                    "minuto": {"Santos": [{"link": "http://minuto"}]},
                }
            }
        }
        with patch.object(ExtraFlyerScraper, "_get_today_str", return_value="10072026"):
            links = s._get_campaign_links(data)
        assert len(links) == 1
        assert links[0]["link"] == "http://mercado"

    def test_falls_back_to_minuto_when_no_mercado(self):
        s = self._make_instance()
        data = {
            "extra": {
                "10072026": {
                    "minuto": {"Santos": [{"link": "http://minuto"}]}
                }
            }
        }
        with patch.object(ExtraFlyerScraper, "_get_today_str", return_value="10072026"):
            links = s._get_campaign_links(data)
        assert len(links) == 1
        assert links[0]["link"] == "http://minuto"

    def test_fallback_to_older_date_when_today_missing(self):
        s = self._make_instance()
        data = {"extra": {"09072026": {"mercado": {"Santos": [{"link": "http://old"}]}}}}
        with patch.object(ExtraFlyerScraper, "_get_today_str", return_value="10072026"):
            links = s._get_campaign_links(data)
        assert len(links) == 1
        assert links[0]["link"] == "http://old"


class TestPaoFlyerScraper:
    def test_campaign_type_is_pao_de_acucar(self):
        assert PaoFlyerScraper.CAMPAIGN_TYPE == "pao-de-acucar"

    def test_brand_is_pao(self):
        assert PaoFlyerScraper.BRAND == "pao"
