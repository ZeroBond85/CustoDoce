"""Browser pool para reutilizar instâncias do Playwright entre scrapers."""

from __future__ import annotations

import asyncio
import contextlib

from playwright.async_api import Browser, BrowserContext, async_playwright

from services.logger import logger


class BrowserPool:
    """Pool de browsers Playwright reutilizáveis."""

    _instance: BrowserPool | None = None
    _browser: Browser | None = None
    _playwright = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_browser(self) -> Browser:
        """Obtém o browser compartilhado, criando se necessário."""
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                if self._browser is not None:
                    with contextlib.suppress(Exception):
                        await self._browser.close()
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-gpu",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                    ],
                )
                logger.info("Playwright browser iniciado (pool)")
            return self._browser

    async def new_context(self, **kwargs) -> BrowserContext:
        """Cria novo contexto no browser compartilhado."""
        browser = await self.get_browser()
        return await browser.new_context(**kwargs)

    async def close(self):
        """Fecha o browser do pool."""
        async with self._lock:
            if self._browser is not None:
                with contextlib.suppress(Exception):
                    await self._browser.close()
                self._browser = None
            if self._playwright is not None:
                with contextlib.suppress(Exception):
                    await self._playwright.stop()
                self._playwright = None
            logger.info("Playwright browser pool fechado")


# Instância global do pool
_browser_pool = BrowserPool()


async def get_browser_pool() -> BrowserPool:
    """Obtém a instância singleton do pool."""
    return _browser_pool


async def close_browser_pool():
    """Fecha o pool global."""
    await _browser_pool.close()
