"""Filtro "Lançamento" (Central do Confeiteiro) aplicado em AMBOS os caminhos
de parsing: loop HTML e _parse_jsonld.

Regressão: antes, o filtro só rodava no loop HTML (website_scraper.py) e o
_parse_jsonld retornava cedo, deixando placeholders "Lançamento" bypassarem
e poluírem a review_queue (200+ itens em 2026-08-15).
"""

from scrapers.website_scraper import WebsiteScraper

_CFG = {
    "name": "Central Teste",
    "base_url": "https://example.com",
    "type": "website_catalog",
    "browse_urls": ["https://example.com/busca?palavra_busca=chocolate"],
}

JSONLD_WITH_LANCAMENTO = """
<html><body>
<script type="application/ld+json">
{
  "@type": "ItemList",
  "itemListElement": [
    {"item": {"name": "Chocolate 50% 1kg", "offers": {"price": 39.9}}},
    {"item": {"name": "Lançamento", "offers": {"price": 0}}},
    {"item": {"name": "Lançamento\\n\\n", "offers": {"price": 25.0}}},
    {"item": {"name": "Gotas Meio Amargo 1kg", "offers": {"price": 44.9}}}
  ]
}
</script>
</body></html>
"""


def _make_scraper() -> WebsiteScraper:
    return WebsiteScraper(_CFG)


def test_jsonld_filtra_lancamento():
    scraper = _make_scraper()
    products = scraper._parse_jsonld(JSONLD_WITH_LANCAMENTO)
    names = [p["product"] for p in products]
    assert "Chocolate 50% 1kg" in names
    assert "Gotas Meio Amargo 1kg" in names
    assert not any("Lançamento" in n for n in names)
    assert len(products) == 2


def test_parse_products_jsonld_nao_retorna_lancamento():
    scraper = _make_scraper()
    products = scraper.parse_products(JSONLD_WITH_LANCAMENTO)
    names = [p["product"] for p in products]
    assert not any("Lançamento" in n for n in names)
    assert len(products) == 2


def test_skip_lancamento_variantes():
    scraper = _make_scraper()
    assert scraper._skip_lancamento("Lançamento")
    assert scraper._skip_lancamento("lançamento")
    assert scraper._skip_lancamento("Lançamento\n\n")
    assert scraper._skip_lancamento("  Lançamento  ")
    assert not scraper._skip_lancamento("Chocolate 50% 1kg")
    assert not scraper._skip_lancamento("Cobertura Top Lançamento Natal")
