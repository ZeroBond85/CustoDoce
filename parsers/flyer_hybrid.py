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

Cents precision
---------------
The integer ("reais") part of prices and the product names come out accurate.
The *cents* on flyers with heavily stylized superscript centavos are unreliable
straight from geometry (RapidOCR's base model confidently misreads the small
"90" glyph as "06"). To recover them, :func:`extract_from_regions` runs a
per-price crop + re-OCR refinement pass (:func:`_refine_cents`), anchored on the
already-known reais so it only overrides a value when the integer part is
re-confirmed. This costs ~+20s/flyer, so it is env-gated via
``FLYER_HYBRID_REFINE_CENTS`` (ON by default; set to ``0`` to favour speed).
"""
from __future__ import annotations

import io
import json
import os
import re
import threading
import time

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
LLM_CB_THRESHOLD = int(os.environ.get("FLYER_HYBRID_CB_THRESHOLD", "3"))
LLM_CB_COOLDOWN = int(os.environ.get("FLYER_HYBRID_CB_COOLDOWN", "600"))

# Cents refinement: re-OCR an upscaled crop around each reconstructed price to
# recover the stylized superscript "centavos" (RapidOCR's base model misreads
# the small "90" glyph as "06" at flyer scale). This roughly doubles extraction
# time (~+20s/flyer) but materially improves price precision, so it ships ON by
# default; set FLYER_HYBRID_REFINE_CENTS=0 to trade precision for speed.
CENTS_CROP_UPSCALE = int(os.environ.get("FLYER_HYBRID_CENTS_UPSCALE", "6"))

# Minimum raw-OCR name quality (0-1) before LLM refinement is triggered.
# Higher = more blocks sent to LLM (better names, more rate-limit risk).
# Lower = more raw-OCR names kept (faster, full coverage).
QUALITY_THRESHOLD = float(os.environ.get("FLYER_RAW_QUALITY_THRESHOLD", "0.3"))

# Circuit breaker state per provider name.
_cb_state: dict[str, dict] = {}


def _provider_available(name: str) -> bool:
    state = _cb_state.get(name)
    if state is None:
        return True
    if state["open"] and time.time() - state["since"] > LLM_CB_COOLDOWN:
        state["open"] = False
        state["count"] = 0
        logger.info("flyer_hybrid_cb_half_open", provider=name)
        return True
    return not state["open"]


def _provider_failed(name: str):
    state = _cb_state.setdefault(name, {"open": False, "count": 0, "since": 0.0})
    state["count"] += 1
    if state["count"] >= LLM_CB_THRESHOLD:
        state["open"] = True
        state["since"] = time.time()
        logger.info("flyer_hybrid_cb_open", provider=name, count=state["count"])


def _provider_succeeded(name: str):
    state = _cb_state.get(name)
    if state:
        state["count"] = 0
        state["open"] = False


def _reset_cb():
    _cb_state.clear()


def _refine_cents_enabled() -> bool:
    return os.environ.get("FLYER_HYBRID_REFINE_CENTS", "1").lower() not in ("0", "false", "no", "")

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
    return _blocks_from_prices(prices, regions)


def _blocks_from_prices(prices: list[Price], regions: list[dict]) -> list[dict]:
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


# --- cents refinement (crop + re-OCR) ----------------------------------------


def _parse_reocr_cents(txts: list[str] | None, reais: int) -> float | None:
    """Recover ``reais.CC`` from a re-OCR'd price crop, anchored on the known
    integer part so we only override geometry when the reais are confirmed.

    Accepts both separated (``"19 90"``, ``"19,90"``) and concatenated
    (``"1990"``) digit forms; returns None when the reais cannot be confirmed.
    """
    digits = re.sub(r"[^0-9]", " ", " ".join(txts or [])).strip()
    if not digits:
        return None
    r = str(reais)
    # reais followed by a 2-digit cents group (separator collapses to a space)
    m = re.search(rf"\b{r}\s+(\d{{2}})\b", digits)
    if m:
        return reais + int(m.group(1)) / 100
    # concatenated RRCC token (e.g. reais=19 -> "1990")
    for tok in digits.split():
        if tok.startswith(r) and len(tok) == len(r) + 2:
            return reais + int(tok[len(r):]) / 100
    return None


def _refine_cents(image_bytes: bytes, prices: list[Price]) -> list[Price]:
    """Re-OCR an upscaled crop around each price to fix stylized centavos.

    Best-effort: on any failure (no engine, unreadable image, unconfirmed
    reais) the original geometry price is kept unchanged.
    """
    engine = _get_engine()
    if engine is None:
        return prices
    try:
        import numpy as np
        from PIL import Image
    except Exception:
        return prices
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        logger.info("flyer_hybrid_refine_image_error", error=str(exc))
        return prices

    up = max(1, CENTS_CROP_UPSCALE)
    refined: list[Price] = []
    corrected = 0
    for price in prices:
        try:
            xs = [p[0] for p in price.box]
            ys = [p[1] for p in price.box]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            h = y1 - y0
            if h <= 0:
                refined.append(price)
                continue
            crop = img.crop(
                (
                    max(0, int(x0 - h * 0.35)),
                    max(0, int(y0 - h * 0.6)),
                    int(x1 + h * 2.4),
                    int(y1 + h * 0.35),
                )
            )
            if crop.width < 3 or crop.height < 3:
                refined.append(price)
                continue
            big = crop.resize((crop.width * up, crop.height * up), Image.LANCZOS)  # type: ignore[attr-defined]
            res = engine(np.array(big))
            new_value = _parse_reocr_cents(getattr(res, "txts", None), int(price.value))
            if new_value is not None and abs(new_value - price.value) > 0.001:
                refined.append(Price(new_value, price.box, f"{price.source}+reocr"))
                corrected += 1
            else:
                refined.append(price)
        except Exception as exc:
            logger.info("flyer_hybrid_refine_price_error", error=str(exc))
            refined.append(price)
    logger.info("flyer_hybrid_cents_refined", total=len(prices), corrected=corrected)
    return refined


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


def _name_quality(name: str) -> float:
    """Score name quality 0 (garbage) to 1 (perfect).

    Real product names are longer than 4 characters and contain mostly
    alphabetic words. Names shorter than 5 chars or dominated by digits
    / single-character fragments are treated as low quality.
    """
    if len(name) < 5:
        return 0.0
    words = name.split()
    if not words:
        return 0.0
    long_ratio = sum(1 for w in words if len(w) > 2) / len(words)
    digits_ratio = sum(1 for c in name if c.isdigit()) / max(len(name), 1)
    return max(0.0, min(1.0, long_ratio * 0.8 + (1 - digits_ratio) * 0.2))


def _raw_ocr_fallback(blocks: list[dict]) -> list[dict]:
    """Fallback when all text-LLM providers fail: use raw OCR texts as names.

    Each block already has the correct price from geometry and a list of
    nearby OCR text fragments. We concatenate them into a product name.
    """
    products = []
    for b in blocks:
        texts = b.get("texts", [])
        name = " ".join(t for t in texts if len(t) > 1).strip()[:80]
        if name:
            products.append({"product": name, "price": b["price"], "unit": ""})
    if products:
        logger.info("flyer_hybrid_raw_ocr_fallback", count=len(products))
    return products


def resolve_names(blocks: list[dict]) -> list[dict]:
    """Resolve product names from OCR price blocks (raw-OCR-first strategy).

    Guarantees 100 % coverage by always starting with raw-OCR names. LLM
    providers are called *only* for blocks whose raw-OCR name scores below
    ``QUALITY_THRESHOLD``. This eliminates the sequential LLM wait that caused
    empty results when all providers rate-limited.

    Returns normalized ``{"product", "price", "unit"}`` dicts — never empty
    when blocks have at least one non-empty text.
    """
    if not blocks:
        return []

    products = _raw_ocr_fallback(blocks)
    if not products:
        return []

    low_idx = [i for i, p in enumerate(products) if _name_quality(p.get("product", "")) < QUALITY_THRESHOLD]
    if not low_idx:
        logger.info("flyer_hybrid_all_names_ok_llm_skipped", count=len(products))
        return products

    providers = _text_llm_providers()
    if not providers:
        logger.info("flyer_hybrid_no_text_llm_key")
        return products

    low_blocks = [blocks[i] for i in low_idx]
    payload = json.dumps(low_blocks, ensure_ascii=False)

    for prov in providers:
        if not _provider_available(prov["name"]):
            logger.info("flyer_hybrid_cb_skipping", provider=prov["name"])
            continue
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
                    "messages": [{"role": "user", "content": _NAME_PROMPT + payload}],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
                timeout=LLM_TIMEOUT,
            )
            if resp.status_code == 429:
                logger.info("flyer_hybrid_llm_429", provider=prov["name"])
                _provider_failed(prov["name"])
                continue
            if resp.status_code >= 400:
                logger.info("flyer_hybrid_llm_http_error", provider=prov["name"], status=resp.status_code)
                continue
            content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            items = _parse_llm_json(content)
            if items is None:
                logger.info("flyer_hybrid_llm_bad_json", provider=prov["name"])
                continue
            refined = _to_products(items)
            if not refined:
                continue
            for i, r in zip(low_idx, refined, strict=True):
                if r.get("product"):
                    products[i]["product"] = r["product"]
            _provider_succeeded(prov["name"])
            logger.info("flyer_hybrid_names_refined", provider=prov["name"], refined=len(refined), total=len(products))
            return products
        except Exception as exc:
            logger.info("flyer_hybrid_llm_error", provider=prov["name"], error=str(exc))
            _provider_failed(prov["name"])
            continue

    logger.info("flyer_hybrid_no_refinement_raw_ocr_kept", low_count=len(low_idx))
    return products


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


def extract_from_regions(regions: list[dict], image_bytes: bytes | None = None) -> list[dict] | None:
    """Full hybrid pipeline from OCR regions to products (blocks + text-LLM).

    When ``image_bytes`` is provided and cents refinement is enabled, each
    reconstructed price is re-OCR'd from an upscaled crop to fix stylized
    centavos before the blocks are built.
    """
    prices = deduplicate_dual_prices(reconstruct_prices(regions))
    if not prices:
        return None
    if image_bytes and _refine_cents_enabled():
        prices = _refine_cents(image_bytes, prices)
    blocks = _blocks_from_prices(prices, regions)
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
    return extract_from_regions(regions, image_bytes=image_bytes)


__all__ = [
    "DENSITY_THRESHOLD",
    "QUALITY_THRESHOLD",
    "build_price_blocks",
    "extract_from_regions",
    "extract_products_hybrid",
    "is_dense",
    "resolve_names",
    "run_rapidocr",
]
