"""Testes para a extracao de flyers do PlaywrightAggregatorScraper, com foco
no fallback de resiliencia quando o seletor de card do agregador quebra
(caso Promotons: classes CSS mudam e retornam 0 candidatos).
"""
from __future__ import annotations

from scrapers.playwright_scraper import PlaywrightAggregatorScraper


class _AsyncList:
    def __init__(self, items):
        self._items = items

    def __await__(self):
        async def _():
            return self._items
        return _().__await__()


class _MockCard:
    def __init__(self, href: str, inner: str = ""):
        self._href = href
        self._inner = inner

    async def inner_html(self):
        return self._inner

    async def get_attribute(self, name):
        if name == "href":
            return self._href
        return None

    async def query_selector(self, sel):
        return None

    async def query_selector_all(self, sel):
        return []

    async def inner_text(self):
        return "Folheto Promotons"


class _MockPage:
    def __init__(self, cards_for_selector: list, cards_for_a: list):
        self._cards_for_selector = cards_for_selector
        self._cards_for_a = cards_for_a

    async def query_selector_all(self, selector: str):
        if selector == "a[href]":
            return self._cards_for_a
        # seletor de card especifico do portal
        return self._cards_for_selector

    async def content(self):
        return "<html></html>"


def _make_scraper(name="Promotons"):
    return PlaywrightAggregatorScraper(
        {"name": name, "base_url": "https://www.promotons.com.br", "regions": ["santos"]}
    )


def test_extract_flyers_from_card_selector():
    scraper = _make_scraper()
    # card real encontrado pelo seletor de classe
    card = _MockCard("", inner='<a href="/brochure/loja-x">ver</a><img src="https://na.leafletscdn.com/x.jpg"/>')
    page = _MockPage(cards_for_selector=[card], cards_for_a=[])
    flyers = scraper._extract_flyers(page, "promotons")
    # transforma corotina em lista
    import asyncio
    result = asyncio.run(flyers)
    assert len(result) == 1
    assert "promotons" in result[0]["source"]


def test_extract_flyers_fallback_to_all_links_when_no_cards():
    scraper = _make_scraper()
    # seletor de card quebrado (0) -> fallback varre <a href> da pagina
    a_links = [
        _MockCard("https://www.promotons.com.br/brochure/loja-x"),
        _MockCard("https://www.promotons.com.br/encarte/loja-y"),
        _MockCard("https://www.promotons.com.br/about"),  # sem padrao de flyer -> ignorado
    ]
    page = _MockPage(cards_for_selector=[], cards_for_a=a_links)
    import asyncio
    result = asyncio.run(scraper._extract_flyers(page, "promotons"))
    # soh 2 dos 3 <a> casam com padroes de flyer
    assert len(result) == 2
    assert all("brochure" in f.get("flyer_url", "") or "encarte" in f.get("flyer_url", "") for f in result)


def test_extract_flyers_empty_page_returns_empty():
    scraper = _make_scraper()
    page = _MockPage(cards_for_selector=[], cards_for_a=[])
    import asyncio
    result = asyncio.run(scraper._extract_flyers(page, "promotons"))
    assert result == []
