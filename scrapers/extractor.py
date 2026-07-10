"""
scrapers/extractor.py

Unified product extractor — dispatch entre modos de extração.

Modes:
  text_dense:  texto com estrutura (pdfplumber OK, flyer_parser OK)
  text_sparse: texto solto (OCR raw → preprocessing → parser)
  pdf_page:    PDF → render → OCR (fallback quando pdfplumber falha)

Feature flags em config/features.yaml:
  extractor.mode: "auto" | "text_dense" | "text_sparse" | "pdf_page"
  extractor.preprocess: true
  extractor.save_ocr_text: true
"""

import io
import logging
import re

from PIL import Image, ImageOps
from scrapers.flyer_parser import extract_lines_from_text, parse_flyer_lines

logger = logging.getLogger(__name__)

# ── Detectores de modo ──────────────────────────────────────────

_DENSE_THRESHOLD = 0.3
_PRICE_LINE_RE = re.compile(r"R?\s*[$]\s*\d[\d.,]*", re.I)
_TABLE_SEP_RE = re.compile(r"\s{3,}")


def _estimate_density(text: str) -> float:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return 0.0
    scored = 0
    for line in lines:
        has_price = bool(_PRICE_LINE_RE.search(line))
        has_cols = bool(_TABLE_SEP_RE.search(line))
        if has_price or has_cols:
            scored += 1
    return scored / len(lines)


def _auto_detect_mode(text: str) -> str:
    density = _estimate_density(text)
    if density >= _DENSE_THRESHOLD:
        return "text_dense"
    return "text_sparse"


# ── Pré-processamento de imagem ─────────────────────────────────

def preprocess_image(image_bytes: bytes) -> bytes:
    """Aplica preprocessing para melhorar OCR:
    1. Grayscale
    2. Binarização (threshold adaptativo ou Otsu)
    3. Retorna bytes PNG processados.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        # Grayscale
        img = ImageOps.grayscale(img)
        # Aumentar contraste
        img = ImageOps.autocontrast(img, cutoff=5)
        # Binarização simples (threshold)
        img = img.point(lambda x: 0 if x < 140 else 255, "1")
        # Salvar como PNG
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.debug("Preprocessing failed: %s", e)
        return image_bytes


# ── Extração unificada ──────────────────────────────────────────

def extract_products(
    content: bytes | str,
    source_type: str = "auto",
    lang: str = "por",
    mode: str = "auto",
) -> tuple[list[dict], str, str]:
    """Extrai produtos de conteúdo (PDF, imagem, ou texto).
    Args:
        content: bytes do PDF/imagem, ou string de texto
        source_type: "pdf" | "image" | "text"
        lang: idioma OCR
        mode: "auto" | "text_dense" | "text_sparse" | "pdf_page"
    Returns:
        (products, ocr_text, mode_used)
    """
    from scrapers.flyer_parser import (
        extract_lines_from_text,
        parse_flyer_lines,
    )
    from services.config import get_feature

    raw_text = ""
    used_mode = mode

    # ── Phase 1: Extract raw text ─────────────────────────────
    if source_type == "pdf":
        # PDF: try pdfplumber first (text_dense), OCR fallback (pdf_page)
        raw_text = _extract_pdf_text(content, mode)
        if not raw_text:
            raw_text = _ocr_pdf(content, lang)
            used_mode = "pdf_page" if mode == "auto" else mode
        else:
            used_mode = "text_dense" if mode == "auto" else mode

    elif source_type == "image":
        # Image: OCR with preprocessing
        processed = preprocess_image(content) if get_feature("extractor.preprocess", default=True) else content
        raw_text = _ocr_image(processed, lang)
        used_mode = "text_sparse"

    else:
        # String text: use directly
        if isinstance(content, str):
            raw_text = content
        used_mode = "text_dense"

    # ── Phase 2: Detect mode from text density (if auto) ──────
    if mode == "auto" and raw_text:
        if used_mode == "text_dense":
            # já veio de pdfplumber → denso
            pass
        else:
            detected = _auto_detect_mode(raw_text)
            if detected == "text_dense":
                used_mode = "text_sparse"

    # ── Phase 3: Parse into products ──────────────────────────
    if not raw_text:
        return [], "", used_mode

    lines = extract_lines_from_text(raw_text)
    products = parse_flyer_lines(lines)

    return products, raw_text, used_mode


def _extract_pdf_text(content: bytes, mode: str) -> str:
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            texts = []
            for page in pdf.pages:
                t = page.extract_text() or ""
                # Try tables for dense extraction
                if mode == "text_dense" or mode == "auto":
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            row_text = " ".join(c or "" for c in row).strip()
                            if row_text:
                                texts.append(row_text)
                if t:
                    texts.append(t)
            result = "\n".join(texts)
            return result
    except Exception as e:
        logger.debug("pdfplumber failed: %s", e)
        return ""


def _ocr_pdf(content: bytes, lang: str) -> str:
    try:
        from pdf2image import convert_from_bytes
        from pytesseract import image_to_string

        images = convert_from_bytes(content, dpi=300, fmt="jpeg", thread_count=2)
        text_parts = []
        for img in images:
            processed = preprocess_image(img.tobytes())
            img_clean = Image.open(io.BytesIO(processed))
            t = image_to_string(img_clean, lang=lang)
            if t:
                text_parts.append(t)
        return "\n".join(text_parts)
    except Exception as e:
        logger.debug("OCR PDF failed: %s", e)
        return ""


def _ocr_image(image_bytes: bytes, lang: str) -> str:
    try:
        from PIL import Image
        from pytesseract import image_to_string

        img = Image.open(io.BytesIO(image_bytes))
        text = image_to_string(img, lang=lang, config="--psm 6 --oem 3")
        return text.strip()
    except Exception as e:
        logger.debug("OCR image failed: %s", e)
        return ""


__all__ = [
    "extract_products",
    "extract_lines_from_text",
    "parse_flyer_lines",
    "preprocess_image",
]
