from unittest.mock import patch

from PIL import Image

from scrapers import extractor
from scrapers.ocr import ocr_pdf


def _page(*, color=(255, 255, 255)):
    return Image.new("RGB", (40, 20), color)


@patch("scrapers.ocr.image_to_string", return_value="Leite condensado 395g")
@patch("scrapers.ocr.convert_from_bytes")
def test_ocr_pdf_ocrs_pillow_pages(mock_conv, mock_ocr):
    mock_conv.return_value = [_page(), _page()]
    out = ocr_pdf(b"fake-pdf-bytes")
    assert "Leite condensado 395g" in out


@patch("pytesseract.image_to_string", return_value="Creme de leite 200g")
@patch("pdf2image.convert_from_bytes")
def test_extractor_ocr_pdf_ocrs_pillow_pages(mock_conv, mock_ocr):
    mock_conv.return_value = [_page(color=(255, 0, 0))]
    out = extractor._ocr_pdf(b"fake-pdf-bytes", "por")
    assert "Creme de leite 200g" in out
