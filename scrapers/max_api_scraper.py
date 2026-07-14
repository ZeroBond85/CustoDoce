import hashlib

from scrapers.base_web_scraper import BaseWebScraper
from scrapers.flyer_ocr import extract_flyer_products


class MaxApiScraper(BaseWebScraper):
    def __init__(self, store_config: dict):
        super().__init__(store_config)
        self.api_base = store_config.get("api_base", "https://institucional.supermuffato.com.br/webtools/services/api")
        self.api_endpoint = store_config.get("api_endpoint", "sm-rds-ofertas.php")
        self.api_params = store_config.get("api_params", "action=getOffers&store={store_id}")
        # store_id 120 = Max Atacadista Butanta (Sao Paulo capital). store 75 = Parana (nao usar).
        self.store_id = store_config.get("store_id", "120")

    def get_offers(self, store_id: str = None) -> list[dict]:
        sid = store_id or self.store_id
        params = self.api_params.replace("{store_id}", sid)
        url = f"{self.api_base}/{self.api_endpoint}?{params}"
        data = self.fetch_json(url)
        return data.get("offers", []) if isinstance(data, dict) else []

    def parse_offer(self, offer: dict) -> list[dict]:
        entries = []
        flyers = offer.get("flyer", [])

        for flyer in flyers:
            items = flyer.get("item", [])
            for item in items:
                image_url = item.get("image", "")
                if image_url:
                    if image_url.startswith("//"):
                        image_url = "https:" + image_url
                    entries.append(
                        {
                            "product": "Encarte Max Atacadista",
                            "price": 0.0,
                            "unit": "encarte",
                            "image_url": image_url,
                            "image_hash": hashlib.md5(image_url.encode(), usedforsecurity=False).hexdigest(),
                            "flyer_id": item.get("id", ""),
                            "is_cover": item.get("isCover", False),
                        }
                    )
        return entries

    def parse_products(self, raw_data) -> list[dict]:
        return []

    def run(self, ingredients: list[dict]) -> list[dict]:
        image_entries = []
        offers = self.get_offers()
        for offer in offers:
            image_entries.extend(self.parse_offer(offer))

        products = extract_flyer_products(
            self._http, image_entries, self.name, source="max_flyer"
        )
        if products:
            self.report_success(items_found=len(products), products_matched=0, flyer_count=len(image_entries))
        else:
            self.report_failure(
                reason="no products extracted from flyers", items_found=0, products_matched=0
            )
        return products
