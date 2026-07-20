"""Shared flyer image extraction — vision-LLM first, OCR fallback.

Encartes graficos (Roldao/Max/Giga) sao imagens densas onde o Tesseract puro
produz texto-lixo. Por isso a extracao tenta vision-LLM (Groq -> OpenRouter ->
HF) primeiro (gated por features.ai.vision) e so cai para OCR quando a vision
esta indisponivel (sem API key / circuit breaker aberto / flag desligada).

A funcao e pura (nao toca Supabase): recebe um http client, a lista de entradas
de encarte (cada uma com image_url) e devolve produtos normalizados. O self-
healing (record_success/failure) fica a cargo do scraper que a chama.
"""
from __future__ import annotations

import time
from collections.abc import Iterable

import httpx

from parsers.vision_extract import extract_products_via_vision
from scrapers.extractor import extract_products
from services.config import get_feature
from services.logger import logger
from services.url_guard import guard_url


def _download_image(http: httpx.Client, url: str) -> bytes | None:
    # allow_http=True: flyer images are served over http for allowlisted hosts
    # (roldao.com.br etc.). The guard still blocks non-allowlisted hosts and
    # private/metadata IPs (see services.url_guard).
    safe_url = guard_url(url, allow_http=True)
    if not safe_url:
        logger.warning("[flyer_ocr] skipping disallowed image URL: %s", url)
        return None
    for attempt in range(3):
        try:
            resp = http.get(safe_url, follow_redirects=True, timeout=40.0)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            if attempt < 2:
                wait = 2.0 * (attempt + 1)
                logger.warning("[flyer_ocr] download failed %s (attempt %d/3): %s — retrying in %.0fs", url, attempt + 1, exc, wait)
                time.sleep(wait)
            else:
                logger.error("[flyer_ocr] download failed %s (3/3): %s — giving up", url, exc)
                return None
    return None


def _normalize(item: dict, store_name: str, source: str, fallback_validity: str) -> dict | None:
    name = (item.get("product") or "").strip()
    if not name or len(name) < 3:
        return None
    price = item.get("price")
    if price is None:
        return None
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    return {
        "product": name,
        "price": price,
        "unit": item.get("unit", "") or "",
        # Vision retorna 'validity'; OCR retorna 'validity_raw'.
        "validity_raw": item.get("validity") or item.get("validity_raw") or fallback_validity or "",
        "brand": item.get("brand", "") or "",
        "store": store_name,
        "source": source,
    }


def _extract_one(image_bytes: bytes, store_name: str) -> list[dict]:
    """Density-routed extraction: hybrid (dense) -> vision -> OCR fallback.

    Encartes densos (centenas de regioes) sao processados pelo caminho hibrido
    (RapidOCR + reconstrucao geometrica de preco + LLM-texto), onde a vision-LLM
    costuma retornar 0 produtos. Encartes esparsos seguem direto para a vision.
    O roteador so ativa com features.ai.flyer_hybrid e degrada silenciosamente
    para a vision quando RapidOCR/LLM estao ausentes.
    """
    if get_feature("features.ai.flyer_hybrid", default=False):
        try:
            from parsers.flyer_hybrid import extract_products_hybrid

            hybrid = extract_products_hybrid(image_bytes)
            if hybrid:
                logger.info("[flyer_ocr] %s: hibrido denso -> %d produtos", store_name, len(hybrid))
                return hybrid
        except Exception as exc:
            logger.debug("[flyer_ocr] hibrido falhou para %s: %s", store_name, exc)

    try:
        vision = extract_products_via_vision(image_bytes)
    except Exception as exc:
        logger.debug("[flyer_ocr] vision failed for %s: %s", store_name, exc)
        vision = None
    if vision:
        return vision

    try:
        ocr_products, _text, _mode = extract_products(image_bytes, source_type="image")
        return ocr_products or []
    except Exception as exc:
        logger.debug("[flyer_ocr] OCR failed for %s: %s", store_name, exc)
        return []


def extract_flyer_products(
    http: httpx.Client,
    image_entries: Iterable[dict],
    store_name: str,
    source: str = "flyer",
    max_images: int | None = None,
    max_concurrency: int = 1,
) -> list[dict]:
    """Baixa cada encarte e extrai produtos (vision-first -> OCR).

    Imagens processadas em paralelo (asyncio + semaforo) para nao ficar
    sequencial quando ha varios encartes (ex.: Max tem 21 imagens).

    Args:
        http: cliente httpx (usa verify/redirects ja configurados no scraper).
        image_entries: entradas com chave ``image_url`` (+ opcional ``post_date``).
        store_name: nome da loja (para logs e campo ``store``).
        source: rotulo de origem (ex.: ``roldao_flyer``).
        max_images: limite opcional de imagens processadas (free-tier/rate-limit).
        max_concurrency: nivel de paralelismo no vision (default 4).

    Returns:
        Lista de produtos normalizados. Vazia se nada foi extraido.
    """
    import asyncio

    products: list[dict] = []
    seen: set[str] = set()
    counted: set[str] = set()
    total = 0
    for e in image_entries:
        h = e.get("image_hash") or e.get("image_url") or ""
        if e.get("image_url") and h not in counted:
            counted.add(h)
            total += 1
    logger.info("[flyer_ocr] %s: iniciando %d encarte(s) (source=%s, conc=%d)", store_name, total, source, max_concurrency)

    sem = asyncio.Semaphore(max_concurrency)
    processed = 0

    async def _worker(entry: dict) -> list[dict]:
        nonlocal processed
        url = entry.get("image_url")
        if not url:
            return []
        image_hash = entry.get("image_hash") or url
        if image_hash in seen:
            return []
        seen.add(image_hash)
        async with sem:
            loop = asyncio.get_event_loop()
            image_bytes = await loop.run_in_executor(None, _download_image, http, url)
        if not image_bytes:
            logger.warning("[flyer_ocr] %s: encarte falhou ao baixar", store_name)
            return []
        processed_local = processed + 1
        processed = processed_local
        logger.info(
            "[flyer_ocr] %s: encarte %d/%d baixado (%d KB) — extraindo via vision…",
            store_name,
            processed_local,
            total,
            len(image_bytes) // 1024,
        )
        fallback_validity = entry.get("post_date") or entry.get("validity_raw") or ""
        found = 0
        out: list[dict] = []
        for item in _extract_one(image_bytes, store_name):
            norm = _normalize(item, store_name, source, fallback_validity)
            if norm:
                out.append(norm)
                found += 1
        logger.info("[flyer_ocr] %s: encarte %d/%d -> %d produtos", store_name, processed_local, total, found)
        return out

    async def _run() -> list[list[dict]]:
        tasks = []
        idx = 0
        for entry in image_entries:
            if max_images is not None and idx >= max_images:
                logger.info("[flyer_ocr] %s: limite max_images=%d atingido", store_name, max_images)
                break
            if not entry.get("image_url"):
                continue
            h = entry.get("image_hash") or entry.get("image_url")
            if h in seen:
                continue
            idx += 1
            tasks.append(asyncio.ensure_future(_worker(entry)))
        return await asyncio.gather(*tasks)

    results = asyncio.run(_run())
    for r in results:
        products.extend(r)

    logger.info("[flyer_ocr] %s: %d produtos de %d imagens", store_name, len(products), processed)
    return products


__all__ = ["extract_flyer_products"]
