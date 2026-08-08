"""Testes do route interception no PlaywrightPriceScraper.

O scraper bloqueia download de recursos pesados (imagem/fonte/media/stylesheet)
porque o parser usa o DOM HTML — assets visuais são desperdício de banda no CI.
"""

import asyncio

from scrapers.playwright_price_scraper import PlaywrightPriceScraper


def _make_scraper(block_resources=True):
    cfg = {
        "name": "TrayStore",
        "base_url": "https://traytest.com.br",
        "browse_urls": ["https://traytest.com.br/categorias/doces"],
        "block_resources": block_resources,
    }
    return PlaywrightPriceScraper(cfg)


class _FakeRequest:
    def __init__(self, resource_type):
        self.resource_type = resource_type


class _FakeRoute:
    def __init__(self, resource_type):
        self.request = _FakeRequest(resource_type)
        self.aborted = False
        self.continued = False

    async def abort(self):
        self.aborted = True

    async def continue_(self):
        self.continued = True


class _FakeContext:
    def __init__(self):
        self.routes = []

    def route(self, pattern, handler):
        self.routes.append((pattern, handler))


def test_route_blocking_aborts_heavy_resources():
    sc = _make_scraper()
    ctx = _FakeContext()
    sc._setup_route_blocking(ctx)
    assert len(ctx.routes) == 1
    pattern, handler = ctx.routes[0]
    assert pattern == "**/*"

    for rtype in ("image", "font", "media", "stylesheet", "texttrack"):
        route = _FakeRoute(rtype)
        asyncio.run(handler(route))
        assert route.aborted, f"{rtype} deveria ser abortado"
        assert not route.continued


def test_route_blocking_continues_document_and_scripts():
    sc = _make_scraper()
    ctx = _FakeContext()
    sc._setup_route_blocking(ctx)
    _, handler = ctx.routes[0]

    for rtype in ("document", "xhr", "script", "fetch"):
        route = _FakeRoute(rtype)
        asyncio.run(handler(route))
        assert route.continued, f"{rtype} deveria continuar"
        assert not route.aborted


def test_route_blocking_disabled_when_config_false():
    sc = _make_scraper(block_resources=False)
    ctx = _FakeContext()
    sc._setup_route_blocking(ctx)
    assert ctx.routes == []
