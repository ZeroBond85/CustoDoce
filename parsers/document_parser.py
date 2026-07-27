from __future__ import annotations

import io
from collections.abc import Callable

from services.logger import logger


def extract_pdf_text(pdf_bytes: bytes, ocr_fallback: bool = True) -> str:
    """Extract text from a PDF using pdfplumber, with optional OCR fallback."""
    import pdfplumber

    text_parts = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if row:
                            text_parts.append(" | ".join(str(c) for c in row if c))
    except Exception as e:
        logger.warning("pdfplumber error: %s", e)

    text = "\n".join(text_parts)
    if text.strip():
        return text

    if ocr_fallback:
        logger.info("pdfplumber returned empty, trying OCR...")
        try:
            text = ocr_pdf_bytes(pdf_bytes)
        except Exception as e:
            logger.warning("OCR error: %s", e)

    return text


def ocr_pdf_bytes(pdf_bytes: bytes, lang: str = "por") -> str:
    """OCR a multi-page PDF. Falls back from rapidocr to pytesseract."""
    try:
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(pdf_bytes, dpi=300, fmt="jpeg", thread_count=2)
    except Exception as e:
        logger.error("PDF conversion error: %s", e)
        return ""

    text_parts = []
    for page_num, img in enumerate(images, 1):
        try:
            import io as _io
            from PIL import ImageOps

            img_clean = ImageOps.autocontrast(img.convert("L"), cutoff=2)
            buf = _io.BytesIO()
            img_clean.save(buf, format="PNG")
            text = _ocr_image_bytes(buf.getvalue(), lang)
            if text:
                text_parts.append(text)
        except Exception as e:
            logger.error("Page %d error: %s", page_num, e)

    return "\n".join(text_parts)


def _ocr_image_bytes(image_bytes: bytes, lang: str = "por") -> str:
    """OCR a single image. Tries rapidocr first, falls back to pytesseract."""
    try:
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR()
        result, _ = engine(image_bytes)
        if result:
            lines = [line[1] for line in result if line[1]]
            return "\n".join(lines)
    except ImportError:
        pass
    except Exception as e:
        logger.debug("rapidocr error (fallback to tesseract): %s", e)

    try:
        from PIL import Image
        from pytesseract import image_to_string
        return image_to_string(Image.open(io.BytesIO(image_bytes)), lang=lang, config="--psm 6 --oem 3").strip()
    except Exception as e:
        logger.warning("pytesseract error: %s", e)
        return ""


def ocr_image(image_bytes: bytes, lang: str = "por") -> str:
    """OCR a single image with preprocessing."""
    return _ocr_image_bytes(image_bytes, lang)


def extract_from_regions(
    pdf_bytes: bytes,
    region_detector: Callable | None = None,
) -> list[dict]:
    """Extract price blocks from a PDF using region detection.

    Args:
        pdf_bytes: Raw PDF content.
        region_detector: Optional callable that receives full text and returns
            list of region dicts with 'text', 'bbox'.

    Returns:
        List of extracted regions with 'text' and 'bbox' keys.
    """
    text = extract_pdf_text(pdf_bytes, ocr_fallback=True)

    if not text.strip():
        return []

    if region_detector:
        regions = region_detector(text)
        if regions:
            return regions

    return [{"text": text, "bbox": None}]
