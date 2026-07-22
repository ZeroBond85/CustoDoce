"""Testes para a extracao de flyers do PlaywrightAggregatorScraper, com foco
no fallback de resiliencia quando o seletor de card do agregador quebra.
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
        return "Folheto"


class _MockPage:
    def __init__(self, cards_for_selector: list, cards_for_a: list):
        self._cards_for_selector = cards_for_selector
        self._cards_for_a = cards_for_a

    async def query_selector_all(self, selector: str):
        if selector == "a[href]":
            return self._cards_for_a
        return self._cards_for_selector

    async def content(self):
        return "<html></html>"


def _make_scraper(name="Kimbino"):
    return PlaywrightAggregatorScraper(
        {"name": name, "base_url": "https://www.kimbino.com.br", "regions": ["santos"]}
    )


def test_extract_flyers_from_card_selector():
    scraper = _make_scraper()
    card = _MockCard("", inner='<a href="/brochure/loja-x">ver</a><img src="https://na.leafletscdn.com/x.jpg"/>')
    page = _MockPage(cards_for_selector=[card], cards_for_a=[])
    flyers = scraper._extract_flyers(page, "kimbino")
    import asyncio
    result = asyncio.run(flyers)
    assert len(result) == 1
    assert "kimbino" in result[0]["source"]


def test_extract_flyers_fallback_to_all_links_when_no_cards():
    scraper = _make_scraper()
    a_links = [
        _MockCard("https://www.kimbino.com.br/brochure/loja-x"),
        _MockCard("https://www.kimbino.com.br/encarte/loja-y"),
        _MockCard("https://www.kimbino.com.br/about"),
    ]
    page = _MockPage(cards_for_selector=[], cards_for_a=a_links)
    import asyncio
    result = asyncio.run(scraper._extract_flyers(page, "kimbino"))
    assert len(result) == 2
    assert all("brochure" in f.get("flyer_url", "") or "encarte" in f.get("flyer_url", "") for f in result)


def test_extract_flyers_empty_page_returns_empty():
    scraper = _make_scraper()
    page = _MockPage(cards_for_selector=[], cards_for_a=[])
    import asyncio
    result = asyncio.run(scraper._extract_flyers(page, "kimbino"))
    assert result == []
