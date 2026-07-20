"""Hybrid dense-flyer extractor: RapidOCR + geometric price + text-LLM names.

Graphical supermarket flyers (Tenda/Roldao/Max) are *dense* images where the
vision-LLM chain frequently returns 0 products (the models cannot read hundreds
of overlapping price/name tokens in one shot) while burning 30-40s per image.

This module takes the opposite approach for dense flyers:

  1. RapidOCR emits hundreds of text regions with bounding boxes.
  2. ``parsers.price_geometry`` reconstructs the *correct* price VALUES from the
     geometry (the LLM's weak spot) and de-duplicates the dual Cliente-APP vs
     Cartao prices.
  3. For each price we gather the nearby product-name regions (a spatial block)
     and ask a text-LLM to compose the clean product NAME (geometry's weak spot).

Density routing lives in :func:`is_dense`; the whole path is gated behind
``features.ai.flyer_hybrid`` and degrades gracefully to the vision chain when
RapidOCR is not installed or no LLM key is configured.
"""
from __future__ import annotations

import json
import os
import threading

from services.http_client import get_client
from services.logger import logger

from .price_geometry import (
    Price,
    deduplicate_dual_prices,
    is_product_name,
    reconstruct_prices,
)

# --- tunables ----------------------------------------------------------------

# Number of RapidOCR regions above which a flyer is considered "dense" and routed
# to this hybrid path instead of the vision-LLM chain. Dense Tenda flyers emit
# ~495-636 regions; sparse product cards stay well below this. Env-overridable
# for tuning without redeploy.
DENSITY_THRESHOLD = int(os.environ.get("FLYER_DENSITY_THRESHOLD", "150"))

# Spatial window (in OCR pixel space) used to associate name regions with a
# price. Names sit above / around the price block on Tenda flyers.
BLOCK_DX = float(os.environ.get("FLYER_BLOCK_DX", "260"))
BLOCK_DY_ABOVE = float(os.environ.get("FLYER_BLOCK_DY_ABOVE", "320"))
BLOCK_DY_BELOW = float(os.environ.get("FLYER_BLOCK_DY_BELOW", "40"))
BLOCK_MAX_TEXTS = int(os.environ.get("FLYER_BLOCK_MAX_TEXTS", "6"))

LLM_TIMEOUT = float(os.environ.get("FLYER_HYBRID_LLM_TIMEOUT", "60"))

# --- RapidOCR runner ---------------------------------------------------------

_engine = None
_engine_lock = threading.Lock()
_engine_unavailable = False


def _get_engine():
    """Lazily build (and cache) a single RapidOCR engine.

    Returns None if RapidOCR is not installed. The engine is thread-safe to
    build once; RapidOCR calls themselves are serialized by the caller (flyer
    OCR runs with a semaphore).
    """
    global _engine, _engine_unavailable
    if _engine is not None:
        return _engine
    if _engine_unavailable:
        return None
    with _engine_lock:
        if _engine is not None:
            return _engine
        if _engine_unavailable:
            return None
        try:
            from rapidocr import RapidOCR

            _engine = RapidOCR()
            logger.info("flyer_hybrid_rapidocr_ready")
        except Exception as exc:  # pragma: no cover - env without rapidocr
            _engine_unavailable = True
            logger.info("flyer_hybrid_rapidocr_unavailable", error=str(exc))
            return None
    return _engine


def run_rapidocr(image_bytes: bytes) -> list[dict] | None:
    """Run RapidOCR on image bytes and return region dicts.

    Each region has the shape consumed by ``price_geometry``::

        {"text": str, "box": [[x, y], [x, y], [x, y], [x, y]], "score": float}

    Returns None when RapidOCR is unavailable or the run fails, so the caller
    can fall back to the vision chain.
    """
    engine = _get_engine()
    if engine is None:
        return None
    try:
        import numpy as np
        from PIL import Image
        import io

        with Image.open(io.BytesIO(image_bytes)) as im:
            arr = np.array(im.convert("RGB"))
        result = engine(arr)
    except Exception as exc:
        logger.info("flyer_hybrid_ocr_failed", error=str(exc))
        return None

    boxes = getattr(result, "boxes", None)
    txts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)
    if boxes is None or txts is None:
        return None

    regions: list[dict] = []
    for i, txt in enumerate(txts):
        try:
            box = [[float(x), float(y)] for x, y in boxes[i]]
        except (TypeError, ValueError, IndexError):
            continue
        score = 0.0
        if scores is not None:
            try:
                score = float(scores[i])
            except (TypeError, ValueError, IndexError):
                score = 0.0
        regions.append({"text": str(txt), "box": box, "score": score})
    return regions


def is_dense(regions: list[dict]) -> bool:
    """True if the flyer has enough OCR regions to warrant the hybrid path."""
    return len(regions) >= DENSITY_THRESHOLD


# --- block builder -----------------------------------------------------------


def _cx(box: list[list[float]]) -> float:
    return sum(p[0] for p in box) / 4


def _cy(box: list[list[float]]) -> float:
    return sum(p[1] for p in box) / 4


def build_price_blocks(regions: list[dict]) -> list[dict]:
    """Pair each reconstructed price with its nearby product-name texts.

    Returns a list of ``{"price": float, "texts": [str, ...]}`` blocks ordered
    the same way the prices were reconstructed. Pure geometry, no network — so
    it is fully unit-testable against OCR fixtures.
    """
    prices: list[Price] = deduplicate_dual_prices(reconstruct_prices(regions))
    names = [r for r in regions if is_product_name(r.get("text", ""))]

    blocks: list[dict] = []
    for price in prices:
        px, py = _cx(price.box), _cy(price.box)
        nearby: list[tuple[float, str]] = []
        for r in names:
            tx, ty = _cx(r["box"]), _cy(r["box"])
            if -BLOCK_DX < (tx - px) < BLOCK_DX and -BLOCK_DY_ABOVE < (ty - py) < BLOCK_DY_BELOW:
                nearby.append((ty, r["text"]))
        nearby.sort()
        blocks.append(
            {
                "price": round(price.value, 2),
                "texts": [t for _, t in nearby][-BLOCK_MAX_TEXTS:],
            }
        )
    return blocks


# --- text-LLM name resolution ------------------------------------------------

_NAME_PROMPT = (
    "Voce recebe blocos extraidos de um encarte de supermercado. Cada bloco tem "
    "um PRECO (ja correto, NAO altere) e TEXTOS proximos vindos de OCR. Para cada "
    "bloco, componha o NOME do produto a partir dos textos, corrigindo erros de "
    "OCR. IGNORE textos promocionais, tamanhos ou lixo de OCR. Se o bloco nao "
    "tiver um nome de produto real, use null. Responda APENAS JSON no schema: "
    '{"produtos":[{"nome": string|null, "preco": number}]}.\n\nBlocos:\n'
)


def _text_llm_providers() -> list[dict]:
    """Ordered text-LLM providers for name resolution (OpenAI-compatible).

    Reuses the same free-tier keys as the rest of the pipeline. Skipped silently
    when a key is absent.
    """
    providers: list[dict] = []
    groq = os.environ.get("GROQ_API_KEY", "")
    if groq:
        providers.append(
            {
                "name": "groq",
                "url": "https://api.groq.com/openai/v1/chat/completions",
                "key": groq,
                "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            }
        )
    openrouter = os.environ.get("OPENROUTER_API_KEY", "")
    if openrouter:
        providers.append(
            {
                "name": "openrouter",
                "url": "https://openrouter.ai/api/v1/chat/completions",
                "key": openrouter,
                "model": os.environ.get("OPENROUTER_MODEL", "openrouter/free"),
            }
        )
    gh = os.environ.get("GH_MODELS_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
    if gh:
        providers.append(
            {
                "name": "github_models",
                "url": "https://models.inference.ai.azure.com/chat/completions",
                "key": gh,
                "model": "gpt-4o-mini",
            }
        )
    return providers


def _parse_llm_json(content: str) -> list[dict] | None:
    """Extract the produtos list from an LLM JSON response, robust to fences."""
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        parts = text.split("```", 2)
        text = parts[1] if len(parts) > 1 else content
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        items = data.get("produtos", [])
        return items if isinstance(items, list) else None
    return None


def resolve_names(blocks: list[dict]) -> list[dict]:
    """Ask a text-LLM to compose product names for price blocks.

    Returns normalized ``{"product", "price", "unit"}`` dicts. Empty list when
    no provider is configured or every provider fails, so the caller can fall
    back to the vision chain.
    """
    if not blocks:
        return []
    providers = _text_llm_providers()
    if not providers:
        logger.info("flyer_hybrid_no_text_llm_key")
        return []

    payload_blocks = json.dumps(blocks, ensure_ascii=False)
    for prov in providers:
        try:
            headers = {
                "Authorization": f"Bearer {prov['key']}",
                "Content-Type": "application/json",
            }
            if prov["name"] == "openrouter":
                headers["HTTP-Referer"] = "https://github.com/anomalyco/custodoce"
            resp = get_client().post(
                prov["url"],
                headers=headers,
                json={
                    "model": prov["model"],
                    "messages": [{"role": "user", "content": _NAME_PROMPT + payload_blocks}],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
                timeout=LLM_TIMEOUT,
            )
            if resp.status_code >= 400:
                logger.info("flyer_hybrid_llm_http_error", provider=prov["name"], status=resp.status_code)
                continue
            content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            items = _parse_llm_json(content)
            if items is None:
                logger.info("flyer_hybrid_llm_bad_json", provider=prov["name"])
                continue
            products = _to_products(items)
            if products:
                logger.info("flyer_hybrid_names_resolved", provider=prov["name"], count=len(products))
                return products
        except Exception as exc:
            logger.info("flyer_hybrid_llm_error", provider=prov["name"], error=str(exc))
            continue
    return []


def _to_products(items: list[dict]) -> list[dict]:
    """Normalize LLM output into the product shape flyer_ocr expects."""
    products: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = it.get("nome") or it.get("product") or it.get("name")
        price = it.get("preco", it.get("price"))
        if not name or price is None:
            continue
        try:
            price_f = float(price)
        except (TypeError, ValueError):
            continue
        if price_f <= 0:
            continue
        products.append({"product": str(name).strip(), "price": price_f, "unit": ""})
    return products


# --- orchestration -----------------------------------------------------------


def extract_from_regions(regions: list[dict]) -> list[dict] | None:
    """Full hybrid pipeline from OCR regions to products (blocks + text-LLM)."""
    blocks = build_price_blocks(regions)
    if not blocks:
        return None
    products = resolve_names(blocks)
    return products or None


def extract_products_hybrid(image_bytes: bytes) -> list[dict] | None:
    """Run the whole hybrid path from image bytes.

    Returns None when RapidOCR is unavailable, the flyer is not dense, or no
    products could be resolved — signalling the caller to use the vision chain.
    """
    regions = run_rapidocr(image_bytes)
    if not regions or not is_dense(regions):
        return None
    return extract_from_regions(regions)


__all__ = [
    "DENSITY_THRESHOLD",
    "build_price_blocks",
    "extract_from_regions",
    "extract_products_hybrid",
    "is_dense",
    "resolve_names",
    "run_rapidocr",
]
