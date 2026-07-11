"""Pao de Acucar Fresh flyer scraper — herda de ExtraFlyerScraper."""

from __future__ import annotations

from scrapers.extra_flyer_scraper import ExtraFlyerScraper


class PaoFlyerScraper(ExtraFlyerScraper):
    """Scraper para folhetos digitais do Pao de Acucar Fresh.

    Mesma plataforma do Extra (folheteria.clubeextra.com.br/campanhas.js),
    mas com brand='pao' e campaign_type='fresh'.
    """

    BRAND = "pao"
    CAMPAIGN_TYPE = "pao-de-acucar"
