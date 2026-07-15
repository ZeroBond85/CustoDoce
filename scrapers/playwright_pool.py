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
        """Obtém o browser compartilhado, criando se necessário.

        Inclui retry de launch (o lançamento do Chromium pode falhar
        esporadicamente no CI por contenção de recursos) e args anti-detecção
        para reduzir bloqueio por WAF/Cloudflare em lojas protegidas.
        """
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                if self._browser is not None:
                    with contextlib.suppress(Exception):
                        await self._browser.close()
                self._playwright = await async_playwright().start()
                launch_args = [
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-zygote",
                ]
                last_err: Exception | None = None
                for attempt in range(3):
                    try:
                        self._browser = await self._playwright.chromium.launch(
                            headless=True,
                            args=launch_args,
                            timeout=60000,
                        )
                        break
                    except Exception as exc:  # noqa: BLE001 - retry de launch
                        last_err = exc
                        logger.warning(
                            "Playwright launch tentativa %d/3 falhou: %s", attempt + 1, exc
                        )
                        await asyncio.sleep(min(2 * (attempt + 1), 10))
                else:
                    if last_err:
                        raise last_err
                logger.info("Playwright browser iniciado (pool)")
            return self._browser

    async def new_context(self, **kwargs) -> BrowserContext:
        """Cria novo contexto no browser compartilhado.

        Aplica um timeout de navegação generoso por padrão (60s) para não
        depender do default frágil do Playwright.
        """
        browser = await self.get_browser()
        kwargs.setdefault("viewport", {"width": 1366, "height": 768})
        context = await browser.new_context(**kwargs)
        context.set_default_timeout(60000)
        context.set_default_navigation_timeout(60000)
        return context

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
