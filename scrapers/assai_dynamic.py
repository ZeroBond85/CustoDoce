"""Assaí Flyer - scraper dinâmico com Playwright.

O Assaí mudou de PDF estático para página JS dinâmica.
URL antiga (404): /printpdf/ofertas/{state}/{store_slug}
URL nova: https://www.assai.com.br/ofertas/{state}
A página carrega via JS e o PDF é gerado dinamicamente.
"""

from __future__ import annotations

import asyncio
from datetime import date

from services.logger import logger
from services.cache_manager import CacheManager
from parsers.document_parser import extract_pdf_text


class AssaiDynamicScraper:
    store: dict
    name: str
    _cache: CacheManager

    def __init__(self, store_config: dict, cache_dir: str = ""):
        self.store = store_config
        self.name = store_config.get("name", "Assaí Atacadista")
        state = store_config.get("state", "sp")
        self.base_url = f"https://www.assai.com.br/ofertas/{state}"
        self._cache = CacheManager(cache_dir=cache_dir)

    @property
    def store_name(self) -> str:
        return self.name

    def run(self, target_date: date | None = None) -> list[dict]:
        """Main entry point. Sync wrapper around async Playwright."""
        return asyncio.run(self._run_async(target_date))

    async def _run_async(self, target_date: date | None = None) -> list[dict]:
        """Async run: Playwright → download PDF → extract text → parse."""
        pdf_bytes = await self._fetch_pdf_async()
        if not pdf_bytes:
            logger.warning("[%s] No PDF downloaded", self.name)
            return []

        text = extract_pdf_text(pdf_bytes, ocr_fallback=True)
        if not text.strip():
            logger.warning("[%s] Empty text from PDF", self.name)
            return []

        return self._parse_products(text)

    async def _fetch_pdf_async(self) -> bytes | None:
        """Use Playwright to navigate and intercept the PDF download."""
        from playwright.async_api import async_playwright

        pdf_bytes: list[bytes] = []

        async def _on_download(download):
            logger.info("[%s] PDF downloading: %s", self.name, download.suggested_filename)
            pdf_bytes.append(await download.path())

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                accept_downloads=True,
            )
            page = await context.new_page()
            page.on("download", _on_download)

            try:
                logger.info("[%s] Navigating to %s", self.name, self.base_url)
                await page.goto(self.base_url, wait_until="networkidle", timeout=30000)

                await page.wait_for_timeout(2000)

                pdf_links = await page.query_selector_all('a[href$=".pdf"], a[download]')
                for link in pdf_links:
                    href = await link.get_attribute("href")
                    if href:
                        logger.info("[%s] Found PDF link: %s", self.name, href)
                        pdf_url = href if href.startswith("http") else f"https://www.assai.com.br{href}"
                        try:
                            import httpx
                            resp = httpx.get(pdf_url, timeout=30)
                            if resp.status_code == 200 and resp.content[:4] == b"%PDF":
                                await browser.close()
                                return resp.content
                        except Exception as e:
                            logger.debug("[%s] Direct PDF fetch failed: %s", self.name, e)

                pdf_button = await page.query_selector('button:has-text("PDF"), a:has-text("PDF"), [class*="download"]:has-text("PDF")')
                if pdf_button:
                    logger.info("[%s] Clicking PDF button", self.name)
                    async with page.expect_download(timeout=15000) as dl_info:
                        await pdf_button.click()
                    download = await dl_info.value
                    path = await download.path()
                    if path:
                        with open(path, "rb") as f:
                            data = f.read()
                        await browser.close()
                        return data

                logger.warning("[%s] No PDF found on page", self.name)
            except Exception as e:
                logger.error("[%s] Playwright error: %s", self.name, e)
            finally:
                await browser.close()

        return pdf_bytes[0] if pdf_bytes else None

    def _parse_products(self, text: str) -> list[dict]:
        """Parse product lines from extracted text.

        Fallback parse — the actual parsing is done by the shared
        flyer_parser pipeline. This method extracts raw lines.
        """
        from scrapers.flyer_parser import extract_lines_from_text, parse_flyer_lines

        lines = extract_lines_from_text(text)
        return parse_flyer_lines(lines)

    def close(self):
        pass
