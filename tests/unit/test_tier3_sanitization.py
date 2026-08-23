"""Regressão Sprint 19 — F5: sanitização Tier 3.

Prod tinha raw_product com conteúdo de <script>/<style> (páginas Vue) e nomes
gigantes de layout. Fix em 2 camadas:
1. website_scraper._extract_name remove script/style/noscript antes de .text()
2. collector.process_price_match normaliza whitespace e limita a 300 chars
"""

import re
from unittest.mock import MagicMock, patch

from scrapers.website_scraper import WebsiteScraper
from services.collector import process_price_match


class _FakeNode:
    """Node selectolax-like mínimo p/ testar decompose."""

    def __init__(self, html: str):
        self.html = html
        self.children: list[_FakeNode] = []

    def css(self, selector: str):
        if selector in ("script", "style", "noscript"):
            return [c for c in self.children if c.tag == selector]
        return []

    def text(self) -> str:
        return re.sub(r"<[^>]+>", " ", self.html)


def _scraper_with_selectors():
    s = WebsiteScraper.__new__(WebsiteScraper)
    s.selectors = {
        "product_card": [".card"],
        "product_name": [],
        "product_price": [],
    }
    return s


def test_extract_name_remove_script_style():
    s = _scraper_with_selectors()
    node = MagicMock()
    junk = {tag: MagicMock() for tag in ("script", "style", "noscript")}
    node.css.side_effect = lambda sel: [junk[sel]] if sel in junk else []
    node.text.return_value = "  Granulado   Harald 1kg \n"

    name = s._extract_name(node)

    assert name == "Granulado Harald 1kg"
    for j in junk.values():
        j.decompose.assert_called_once()


def test_sanitize_name_trunca_e_normaliza():
    assert WebsiteScraper._sanitize_name("  A\n\nB   C  ") == "A B C"
    long = "x" * 500
    out = WebsiteScraper._sanitize_name(long)
    assert len(out) == 300
    assert WebsiteScraper._sanitize_name("   ") is None


@patch("services.collector.has_ingredient_keyword", return_value=True)
@patch("services.collector.match_ingredient")
@patch("services.collector.upsert_price")
def test_process_price_match_sanitiza_entrada(mock_upsert, mock_match, mock_kw):
    from services.types import Ingredient

    ing: Ingredient = {
        "canonical_name": "Manteiga",
        "brands": ["Aviação"],
        "aliases": [],
        "search_terms": ["manteiga"],
        "exclude_terms": [],
    }
    mock_match.return_value = (ing, 100.0, "exato")

    contaminated = f"Manteiga Aviação 500g {'var x=1;' * 200}"
    entry = process_price_match(
        {"id": "loja", "name": "Loja", "type": "website_catalog", "tier": 3},
        contaminated,
        10.0,
        "500g",
        [ing],
    )

    assert entry is not None
    assert len(entry["raw_product"]) <= 300
    # whitespace interno normalizado
    assert "\n" not in entry["raw_product"] and "  " not in entry["raw_product"]


@patch("services.collector.has_ingredient_keyword", return_value=True)
def test_process_price_match_texto_vazio_retorna_none(mock_kw):
    assert process_price_match({"name": "L"}, "   \n\t ", 1.0, "1kg", []) is None
