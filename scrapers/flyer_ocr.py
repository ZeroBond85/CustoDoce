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

from collections.abc import Iterable

import httpx

from parsers.vision_extract import extract_products_via_vision
from scrapers.extractor import extract_products
from services.logger import logger


def _download_image(http: httpx.Client, url: str) -> bytes | None:
    try:
        resp = http.get(url, follow_redirects=True, timeout=40.0)
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        logger.warning("[flyer_ocr] download failed %s: %s", url, exc)
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
    """Vision-first, OCR fallback. Retorna a lista bruta de itens extraidos."""
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
) -> list[dict]:
    """Baixa cada encarte e extrai produtos (vision-first -> OCR).

    Args:
        http: cliente httpx (usa verify/redirects ja configurados no scraper).
        image_entries: entradas com chave ``image_url`` (+ opcional ``post_date``).
        store_name: nome da loja (para logs e campo ``store``).
        source: rotulo de origem (ex.: ``roldao_flyer``).
        max_images: limite opcional de imagens processadas (free-tier/rate-limit).

    Returns:
        Lista de produtos normalizados. Vazia se nada foi extraido.
    """
    products: list[dict] = []
    seen: set[str] = set()
    processed = 0
    counted: set[str] = set()
    total = 0
    for e in image_entries:
        h = e.get("image_hash") or e.get("image_url") or ""
        if e.get("image_url") and h not in counted:
            counted.add(h)
            total += 1
    logger.info("[flyer_ocr] %s: iniciando %d encarte(s) (source=%s)", store_name, total, source)
    for entry in image_entries:
        if max_images is not None and processed >= max_images:
            logger.info("[flyer_ocr] %s: limite max_images=%d atingido", store_name, max_images)
            break
        url = entry.get("image_url")
        if not url:
            continue
        image_hash = entry.get("image_hash") or url
        if image_hash in seen:
            continue
        seen.add(image_hash)

        image_bytes = _download_image(http, url)
        if not image_bytes:
            logger.warning("[flyer_ocr] %s: encarte %d/%d falhou ao baixar", store_name, processed + 1, total)
            continue
        processed += 1
        logger.info("[flyer_ocr] %s: encarte %d/%d baixado (%d KB) — extraindo via vision…", store_name, processed, total, len(image_bytes) // 1024)

        fallback_validity = entry.get("post_date") or entry.get("validity_raw") or ""
        found = 0
        for item in _extract_one(image_bytes, store_name):
            norm = _normalize(item, store_name, source, fallback_validity)
            if norm:
                products.append(norm)
                found += 1
        logger.info("[flyer_ocr] %s: encarte %d/%d -> %d produtos", store_name, processed, total, found)

    logger.info("[flyer_ocr] %s: %d produtos de %d imagens", store_name, len(products), processed)
    return products


__all__ = ["extract_flyer_products"]
