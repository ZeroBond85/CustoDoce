import io
from services.logger import logger

from pdf2image import convert_from_bytes
from pytesseract import image_to_string


def ocr_pdf(pdf_bytes: bytes, lang: str = "por") -> str:
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
            text = image_to_string(img, lang=lang)
            if text:
                text_parts.append(text)
        except Exception as e:
            logger.error("Page %d error: %s", page_num, e)

    return "\n".join(text_parts)


def ocr_image_bytes(image_bytes: bytes, lang: str = "por") -> str:
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        text = image_to_string(img, lang=lang)
        return text.strip()
    except Exception as e:
        logger.error("Image error: %s", e)
        return ""
