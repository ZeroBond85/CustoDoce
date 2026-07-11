import io

from pdf2image import convert_from_bytes
from PIL import Image, ImageOps
from pytesseract import image_to_string

from services.logger import logger


def ocr_pdf(pdf_bytes: bytes, lang: str = "por") -> str:
    """OCR multi-page PDF with preprocessing per page."""
    try:
        images = convert_from_bytes(
            pdf_bytes,
            dpi=300,
            fmt="jpeg",
            thread_count=2,
        )
    except Exception as e:
        logger.error("PDF conversion error: %s", e)
        return ""

    text_parts = []
    for page_num, img in enumerate(images, 1):
        try:
            # Preprocess each page
            processed = preprocess_image(img.tobytes())
            img_clean = Image.open(io.BytesIO(processed))
            t = image_to_string(img_clean, lang=lang)
            if t:
                text_parts.append(t)
        except Exception as e:
            logger.error("Page %d error: %s", page_num, e)

    return "\n".join(text_parts)


def ocr_image_bytes(image_bytes: bytes, lang: str = "por") -> str:
    """OCR single image with preprocessing."""
    try:
        # Preprocess
        processed = preprocess_image(image_bytes)
        img_clean = Image.open(io.BytesIO(processed))
        text = image_to_string(img_clean, lang=lang, config="--psm 6 --oem 3")
        return text.strip()
    except Exception as e:
        logger.error("Image error: %s", e)
        return ""


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
