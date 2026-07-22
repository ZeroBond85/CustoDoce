import hashlib

from services.logger import logger

from scrapers.base_web_scraper import BaseWebScraper
from scrapers.flyer_ocr import extract_flyer_products


class MaxApiScraper(BaseWebScraper):
    def __init__(self, store_config: dict):
        super().__init__(store_config)
        self.api_base = store_config.get("api_base", "https://institucional.supermuffato.com.br/webtools/services/api")
        self.api_base_fallbacks = store_config.get("api_base_fallbacks", [])
        self.api_endpoint = store_config.get("api_endpoint", "sm-rds-ofertas.php")
        self.api_params = store_config.get("api_params", "action=getOffers&store={store_id}")
        # store_id 120 = Max Atacadista Butanta (Sao Paulo capital). store 75 = Parana (nao usar).
        self.store_id = store_config.get("store_id", "120")
        self.max_flyer_pages = int(store_config.get("max_flyer_pages", 0)) or 5
        self.image_host = store_config.get("image_host", "institucional.supermuffato.com.br")
        self.image_host_fallbacks = store_config.get("image_host_fallbacks", [])

    def _try_json(self, base: str, store_id: str | None = None) -> dict | list | None:
        """Tenta fetch JSON de `base`; retorna dict/list ou None. Não levanta."""
        sid = store_id or self.store_id
        try:
            url = f"{base}/{self.api_endpoint}?{self.api_params.replace('{store_id}', sid)}"
            return self.fetch_json(url)
        except Exception as e:
            logger.warning("[%s] falha ao consultar API base %s: %s", self.name, base, e)
            return None

    def get_offers(self, store_id: str = None) -> list[dict]:
        sid = store_id or self.store_id
        # Tenta o domínio primário e os fallbacks (DNS pode estar morto em qualquer um).
        candidates = [self.api_base] + list(self.api_base_fallbacks)
        for base in candidates:
            data = self._try_json(base, sid)
            if isinstance(data, dict) and data.get("offers"):
                return data["offers"]
        return []

    def _normalize_image(self, image_url: str) -> str:
        """Corrige URL de imagem: protocol-relative (//) vira https://.

        NÃO troca o host por fallback — o host retornado pela API já é o
        correto (ex.: institucional.supermuffato.com.br). Trocar por um
        fallback que 404a quebra o download do encarte (bug #70).
        """
        if not image_url:
            return image_url
        if image_url.startswith("//"):
            image_url = "https:" + image_url
        return image_url

    def parse_offer(self, offer: dict) -> list[dict]:
        entries = []
        flyers = offer.get("flyer", [])

        for flyer in flyers:
            items = flyer.get("item", [])
            for item in items:
                image_url = self._normalize_image(item.get("image", ""))
                if image_url:
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

        if not image_entries:
            self.report_failure(
                reason="no offers from API (DNS primário e fallbacks vazios)", items_found=0, products_matched=0
            )
            return []

        products, _ = extract_flyer_products(
            self._http, image_entries[:self.max_flyer_pages], self.name, source="max_flyer"
        )
        if products:
            self.report_success(items_found=len(products), products_matched=0, flyer_count=len(image_entries))
        else:
            self.report_failure(
                reason="no products extracted from flyers", items_found=0, products_matched=0
            )
        return products
