"""Tests for scrapers/extractor.py."""

from __future__ import annotations

import io

from PIL import Image

from scrapers import extractor


class TestAutoDetectMode:
    def test_dense_text_with_prices_and_columns(self):
        text = "Produto A R$ 10,00   Produto B R$ 20,00\nProduto C R$ 30,00   Produto D R$ 40,00"
        assert extractor._auto_detect_mode(text) == "text_dense"

    def test_sparse_text_no_prices(self):
        text = "texto solto sem preco aqui apenas palavras aleatorias"
        assert extractor._auto_detect_mode(text) == "text_sparse"


class TestExtractProductsTextMode:
    def test_returns_products_and_mode(self):
        content = "Leite Condensado Moça 395g R$ 10,50\nCreme de Leite 200g R$ 8,90"
        products, raw_text, mode = extractor.extract_products(content, source_type="text")
        assert len(products) == 2
        assert "Leite Condensado" in products[0].get("product", "")
        assert raw_text == content
        assert mode == "text_dense"

    def test_empty_string_returns_empty(self):
        products, raw_text, mode = extractor.extract_products("", source_type="text")
        assert products == []
        assert raw_text == ""
        assert mode == "text_dense"


class TestPreprocessImage:
    def test_returns_png_bytes(self):
        img = Image.new("RGB", (20, 20), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw = buf.getvalue()

        out = extractor.preprocess_image(raw)
        assert out[:8] == b"\x89PNG\r\n\x1a\n"


class TestExtractPdfTextInvalid:
    def test_invalid_bytes_returns_empty(self):
        assert extractor._extract_pdf_text(b"not a pdf", mode="auto") == ""


class TestOcrImageInvalid:
    def test_invalid_bytes_returns_empty(self):
        assert extractor._ocr_image(b"garbage", lang="por") == ""
