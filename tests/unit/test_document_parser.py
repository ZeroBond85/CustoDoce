from __future__ import annotations

from unittest.mock import patch


from parsers.document_parser import extract_from_regions, extract_pdf_text, ocr_image, ocr_pdf_bytes


def _make_minimal_pdf() -> bytes:
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td"
        b"(Hello World) Tj ET\nendstream\nendobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000058 00000 n \n0000000115 00000 n \n0000000266 00000 n \n"
        b"0000000365 00000 n \ntrailer<</Size 6/Root 1 0 R>>\nstartxref\n437\n%%EOF"
    )


def test_extract_pdf_text():
    pdf = _make_minimal_pdf()
    text = extract_pdf_text(pdf, ocr_fallback=False)
    assert isinstance(text, str)


def test_extract_pdf_text_fallback_ocr():
    pdf = _make_minimal_pdf()
    with patch("parsers.document_parser.ocr_pdf_bytes") as mock_ocr:
        mock_ocr.return_value = "OCR text"
        text = extract_pdf_text(pdf, ocr_fallback=True)
        assert isinstance(text, str)


def test_ocr_pdf_bytes_empty_on_bogus():
    result = ocr_pdf_bytes(b"not a pdf")
    assert result == ""


def test_ocr_image_fallback():
    with patch("parsers.document_parser._ocr_image_bytes") as mock_ocr:
        mock_ocr.return_value = "image text"
        result = ocr_image(b"fake_image_bytes")
        assert result == "image text"


def test_extract_from_regions():
    pdf = _make_minimal_pdf()
    result = extract_from_regions(pdf)
    assert isinstance(result, list)


def test_extract_from_regions_with_detector():
    pdf = _make_minimal_pdf()
    def detector(text):
        return [{"text": "region1", "bbox": (0, 0, 100, 50)}]
    result = extract_from_regions(pdf, region_detector=detector)
    assert len(result) >= 1
    assert result[0]["text"] == "region1"


def test_extract_from_regions_empty_pdf():
    result = extract_from_regions(b"")
    assert result == []


@patch("parsers.document_parser._ocr_image_bytes")
def test_ocr_pdf_bytes_calls_ocr(mock_ocr):
    mock_ocr.return_value = "ocr result"
    with patch("pdf2image.convert_from_bytes") as mock_convert:
        from PIL import Image
        img = Image.new("RGB", (100, 100))
        mock_convert.return_value = [img]
        result = ocr_pdf_bytes(b"fake_pdf", lang="por")
        assert isinstance(result, str)


def test_ocr_image_tesseract_fallback():
    with patch("rapidocr_onnxruntime.RapidOCR") as mock_rapid:
        mock_rapid.side_effect = ImportError("no rapidocr")
        with patch("pytesseract.image_to_string") as mock_ts:
            mock_ts.return_value = "tesseract text"
            with patch("PIL.Image.open") as mock_open:
                from PIL import Image
                mock_img = Image.new("RGB", (10, 10))
                mock_open.return_value = mock_img
                result = ocr_image(b"fake_img")
                assert result == "tesseract text"
