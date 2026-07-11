"""
parsers/vision_extract.py

Vision product extractor — extrai produtos de imagens de flyer via LLMs multimodais.
Fallback chain: Groq → OpenRouter → HF → Tesseract puro (fallback final).

Gated behind features.ai.vision (default: false).
API key ausente → degrada silenciosamente sem crash.
"""

import logging

from services.config import get_feature

from .vision_strategies import extract_products_via_vision as _extract_via_vision

logger = logging.getLogger(__name__)


def extract_products_via_vision(image_bytes: bytes) -> list[dict] | None:
    """Tenta extrair produtos da imagem via LLM multimodal.
    Returns lista de produtos ou None se nenhum strategy funcionar.
    """
    if not get_feature("features.ai.vision", default=False):
        return None

    try:
        products = _extract_via_vision(image_bytes)
        if products:
            logger.info("[Vision] %d produtos extraidos", len(products))
        return products
    except Exception as exc:
        logger.debug("Vision extract failed: %s", exc)
        return None
