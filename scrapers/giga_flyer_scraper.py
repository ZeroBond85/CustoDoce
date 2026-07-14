"""Giga Atacado flyer scraper — VTEX IO storefront (JS-rendered encartes).

O Giga esconde 100% dos precos na API VTEX (retorna price 0 mesmo com regionId/
CEP), entao a coleta e feita pelos encartes graficos. A pagina /encartes e um app
VTEX IO onde cada card ja carrega a pagina do folheto em alta resolucao
(~2245x3389) no ``img[class*=encartesSection__image]`` — nao e preciso abrir o
modal "Ver encarte".

Flow:
1. Playwright carrega /encartes (networkidle) e remove overlays (cookie + promo)
   que interceptam eventos/atrasam o render.
2. Extrai src + alt (o alt traz a validade, ex.: "Folheto Semanal - De 13 a 16/07").
3. Reusa flyer_ocr.extract_flyer_products (vision-LLM first -> OCR fallback).
4. Self-healing: report_success/failure().
"""
from __future__ import annotations

import asyncio
import hashlib

from scrapers.base_web_scraper import BaseWebScraper
from scrapers.flyer_ocr import extract_flyer_products
from scrapers.playwright_pool import get_browser_pool
from services.logger import logger

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


class GigaFlyerScraper(BaseWebScraper):
    def __init__(self, store_config: dict):
        super().__init__(store_config)
        self.encartes_url = (
            store_config.get("encartes_url")
            or store_config.get("page_url")
            or (store_config.get("base_url", "").rstrip("/") + "/encartes")
        )
        if not self.encartes_url:
            raise ValueError("giga_flyer_scraper requires 'encartes_url' or 'base_url' in store config")

    def parse_products(self, raw_data) -> list[dict]:
        return []

    def run(self, ingredients: list[dict]) -> list[dict]:
        try:
            image_entries = asyncio.run(self._collect_flyer_images())
        except Exception as exc:
            logger.warning("[%s] falha ao coletar encartes: %s", self.name, exc)
            self.report_failure(reason=f"playwright error: {exc}", items_found=0, products_matched=0)
            return []

        if not image_entries:
            self.report_failure(reason="no flyer images found", items_found=0, products_matched=0)
            return []

        products = extract_flyer_products(self._http, image_entries, self.name, source="giga_flyer")
        if products:
            self.report_success(items_found=len(products), products_matched=0, flyer_count=len(image_entries))
        else:
            self.report_failure(reason="no products extracted from flyers", items_found=0, products_matched=0)
        return products

    async def _collect_flyer_images(self) -> list[dict]:
        logger.info("[%s] Playwright: abrindo browser + pool", self.name)
        pool = await get_browser_pool()
        context = await pool.new_context(user_agent=_UA)
        page = await context.new_page()
        try:
            logger.info("[%s] Playwright: navegando para %s", self.name, self.encartes_url)
            await page.goto(self.encartes_url, wait_until="networkidle", timeout=45000)
            logger.info("[%s] Playwright: pagina carregada, aguardando render (3s)", self.name)
            await page.wait_for_timeout(3000)
            # Overlays (cookie/promo) atrasam ou interceptam; removemos antes de ler.
            await page.evaluate(
                "() => document.querySelectorAll("
                "'[class*=modal_overlay],#onetrust-consent-sdk').forEach(e => e.remove())"
            )
            logger.info("[%s] Playwright: extraindo cards de encarte (img[class*=encartesSection__image])", self.name)
            cards = await page.eval_on_selector_all(
                "img[class*=encartesSection__image]",
                "els => els.map(e => ({src: e.src, alt: e.alt || ''}))",
            )
            logger.info("[%s] Playwright: %d cards encontrados", self.name, len(cards))
        finally:
            await page.close()
            await context.close()

        entries: list[dict] = []
        for card in cards:
            src = card.get("src")
            if not src:
                continue
            entries.append(
                {
                    "image_url": src,
                    "image_hash": hashlib.md5(src.encode(), usedforsecurity=False).hexdigest(),
                    "validity_raw": card.get("alt", ""),
                }
            )
        logger.info("[%s] %d encartes encontrados", self.name, len(entries))
        return entries


__all__ = ["GigaFlyerScraper"]
