"""Unit tests for EcomplusScraper (e-com.plus SSR storefront).

These tests validate product card parsing WITHOUT hitting the network, using a
fixture that mirrors the real BarraDoce card markup:

  * category/listing pages  -> <h3 class="...ui-link..."> for the name
  * search results          -> <h5 class="...ui-link..."> for the name
  * current price           -> <strong class="...text-base-800">
  * old price (strikethrough) -> <s>
  * discount %              -> <span class="uno-zmd234"> -<strong>N</strong>%
"""

from scrapers.ecomplus_scraper import EcomplusScraper

STORE = {
    "name": "BarraDoce",
    "base_url": "https://www.barradoce.com.br",
    "search_url": "https://www.barradoce.com.br/busca?q={query}",
    "browse_urls": ["https://www.barradoce.com.br/categoria/ingredientes"],
    "type": "website_js",
    "scraper": "ecomplus_scraper",
    "rate_limit": 0.0,
    "max_pages": 1,
}

CARD_H3 = """
<a href="/produto/spray-desmoldante-400ml-cake-brasil" class="flex h-full flex-col overflow-hidden rounded bg-white">
  <div class="relative z-10 flex grow flex-col px-4 pb-2.5 pt-4">
    <div class="flex flex-wrap items-start justify-between gap-x-3">
      <div class="text-base-600">
        <strong class="inline-block text-base-800"> R$&nbsp;34,80</strong>
      </div>
    </div>
    <div><div class="h-5"><div class="flex items-center gap-0.5">
      <small class="pl-1 font-semibold text-yellow-600">4.8</small>
      <small class="pl-0.5 text-base-500">(5)</small>
    </div></div>
    <h3 class="text-sm no-underline ui-link line-clamp-3 xl:line-clamp-2 text-base-700 group-hover:text-primary group-hover:underline">Spray Desmoldante (400ml) - Cake Brasil</h3>
    </div>
  </div>
</a>
"""

CARD_H5_DISCOUNT = """
<a href="/produto/chocolate-50-garoto" class="flex h-full flex-col overflow-hidden rounded bg-white">
  <div class="relative z-10 flex grow flex-col px-4 pb-2.5 pt-4">
    <div class="flex flex-wrap items-start justify-between gap-x-3">
      <div class="text-base-600">
        <strong class="inline-block text-base-800"> R$&nbsp;2,96</strong>
        <s> R$&nbsp;14,80</s>
      </div>
    </div>
    <span class="uno-zmd234"> -<strong>80</strong>% </span>
    <div><h5 class="text-sm no-underline ui-link line-clamp-3 text-base-700">Chocolate em Pó 50% Cacau - Garoto 500g</h5></div>
  </div>
</a>
"""

HTML = f"<html><body>{CARD_H3}{CARD_H5_DISCOUNT}</body></html>"


class TestEcomplusScraper:
    def test_parse_products_h3_name(self):
        scraper = EcomplusScraper(STORE)
        results = scraper.parse_products(HTML)
        assert len(results) == 2
        names = {r["product"] for r in results}
        assert "Spray Desmoldante (400ml) - Cake Brasil" in names
        assert "Chocolate em Pó 50% Cacau - Garoto 500g" in names

    def test_parse_products_price(self):
        scraper = EcomplusScraper(STORE)
        results = scraper.parse_products(HTML)
        by_name = {r["product"]: r for r in results}
        assert by_name["Spray Desmoldante (400ml) - Cake Brasil"]["price"] == 34.80
        assert by_name["Chocolate em Pó 50% Cacau - Garoto 500g"]["price"] == 2.96

    def test_parse_products_old_price_and_discount(self):
        scraper = EcomplusScraper(STORE)
        results = scraper.parse_products(HTML)
        by_name = {r["product"]: r for r in results}
        choc = by_name["Chocolate em Pó 50% Cacau - Garoto 500g"]
        assert choc["old_price"] == 14.80
        assert choc["discount_pct"] == 80

    def test_parse_products_source_url(self):
        scraper = EcomplusScraper(STORE)
        results = scraper.parse_products(HTML)
        by_name = {r["product"]: r for r in results}
        assert by_name["Spray Desmoldante (400ml) - Cake Brasil"]["source_url"].endswith(
            "/produto/spray-desmoldante-400ml-cake-brasil"
        )
