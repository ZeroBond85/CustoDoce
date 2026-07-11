"""Consumer tests: MOCK_FLYERS drives flyer_parser (OCR text -> linhas -> produtos)."""

from __future__ import annotations

from scrapers.flyer_parser import extract_lines_from_text, parse_flyer_lines
from tests.unit.fixtures.mock_data import MOCK_FLYERS


def test_mock_flyers_extract_lines_from_ocr_text():
    text = MOCK_FLYERS[0]["ocr_text"]
    lines = extract_lines_from_text(text)
    assert any("Leite Condensado" in line for line in lines)


def test_mock_flyers_parse_lines_extracts_price():
    text = MOCK_FLYERS[0]["ocr_text"]
    lines = extract_lines_from_text(text)
    products = parse_flyer_lines(lines)
    assert len(products) >= 1
    prod = next(p for p in products if "Leite" in p.get("product", ""))
    assert prod["price"] is not None
    assert float(prod["price"]) > 0


def test_mock_flyers_ocr_confidence_present():
    assert MOCK_FLYERS[0]["ocr_confidence"] >= 0.9
