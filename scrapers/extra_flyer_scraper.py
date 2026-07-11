import json
import re
from datetime import UTC, datetime, timedelta

import httpx

from parsers.unit_extractor import extract_unit as _extract_unit
from services.logger import logger

CAMPANHAS_URL = "https://folheteria.clubeextra.com.br/home/sites/assets/js/campanhas.js"
SP_OFFSET = timedelta(hours=-3)

TARGET_CITIES = [
    "São Paulo",
    "Grande São Paulo",
    "Santos",
    "São Vicente",
    "Praia Grande",
    "Mongaguá",
    "Itanhaém",
    "Peruíbe",
]

PRICE_RE = re.compile(r"(?:R\$\s*)?([1-9]\d{0,2}(?:\.\d{3})*\s*,\d{2})\b")
STOP_WORDS = {
    "exclusivo",
    "cliente",
    "clientes",
    "clube",
    "extra",
    "economize",
    "apenas",
    "confira",
    "pagamento",
    "parcele",
    "cartão",
    "cartao",
    "crédito",
    "credito",
    "débito",
    "debito",
    "dinheiro",
    "total",
    "subtotal",
    "desconto",
    "descontos",
    "condições",
    "condicoes",
    "oferta",
    "ofertas",
    "válido",
    "valido",
    "válida",
    "valida",
    "válidas",
    "validas",
    "até",
    "ate",
    "supermercado",
    "mercado",
    "fotos",
    "meramente",
    "ilustrativas",
    "www",
    "http",
    "https",
    "sac",
    "ministério",
    "saúde",
    "adverte",
    "aleitamento",
    "materno",
    "recomendado",
    "continuar",
    "amamentando",
    "ofereça",
    "novos",
    "alimentos",
    "impresso",
    "via",
    "pública",
    "reservada",
    "retificação",
    "veiculadas",
    "informações",
    "casa",
    "0800",
    "telefone",
    "whatsapp",
    "facebook",
    "instagram",
    "aplicativo",
    "baixe",
    "cadastre-se",
    "informe",
    "site",
    "app",
    "cpf",
    "caixa",
    "grátis",
    "rapido",
    "rápido",
    "fácil",
    "facil",
    "economiza",
    "objetos",
    "decoração",
    "decoracao",
    "fazem",
    "parte",
    "preço",
    "preco",
    "estoques",
    "disponibilidade",
    "consulte",
    "loja",
    "próxima",
    "proxima",
    "mais",
    "próximas",
    "próximo",
    "próximos",
    "sabor",
    "sabores",
    "sabore",
    "aproximadamente",
    "embalagem",
    "embalagens",
}
HEADER_CLEANUP = re.compile(
    r"(?:exclusivo\s+cliente|clube\s+extra|extra\s+mercado|"
    r"mercado\s+extra|r\$\s*\d+\s*kg/cada|"
    r"ofertas\s+v[áa]lidas\s+de\s+\d+[\s/\d]*"
    r"|v[áa]lido?\s+de\s+\d+[\s/\d]*)",
    re.I,
)
VALIDITY_DATE_RE = re.compile(
    r"(?:v[áa]lido?\s+de\s+)?(\d{1,2}\s*(?:a\s+)?\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
    re.I,
)


class ExtraFlyerScraper:
    """Scraper para folhetos digitais do Extra (folheteria.clubeextra.com.br).

    Extrai texto OCR pre-extraido do book_config.js de cada campanha.
    Nao precisa de Playwright nem OCR — apenas HTTP puro.
    """

    BRAND = "extra"
    CAMPAIGN_TYPE = "mercado"

    def __init__(self, store: dict):
        self.store = store
        self.store_name = store.get("name", "Extra Folheteria")
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._http.close()

    @staticmethod
    def _get_today_str() -> str:
        sp_now = datetime.now(UTC) + SP_OFFSET
        return sp_now.strftime("%d%m%Y")

    @staticmethod
    def _ddmmyyyy_to_yyyymmdd(date_str: str) -> str:
        """Convert DDMMYYYY to YYYYMMDD for correct comparison."""
        if len(date_str) == 8 and date_str.isdigit():
            return date_str[4:8] + date_str[2:4] + date_str[0:2]
        return date_str  # fallback

    def _fetch_campanhas(self) -> dict | None:
        resp = self._http.get(CAMPANHAS_URL)
        resp.raise_for_status()
        text = resp.text
        eq_idx = text.index("=")
        start = text.index("'", eq_idx) + 1
        close = text.rfind("'")
        raw = text[start:close].replace("\\/", "/")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("JSON decode error: %s", e)
            return None

    def _get_campaign_links(self, data: dict) -> list[dict]:
        today = self._get_today_str()
        brand_data = data.get(self.BRAND, {}) or data.get("extra", {})
        if today not in brand_data:
            available = sorted(brand_data.keys(), reverse=True)
            selected_today = today
            for d in available:
                d_cmp = ExtraFlyerScraper._ddmmyyyy_to_yyyymmdd(d)
                today_cmp = ExtraFlyerScraper._ddmmyyyy_to_yyyymmdd(today)
                if d_cmp <= today_cmp:
                    selected_today = d
                    break
            else:
                logger.warning("No campaign data for %s", today)
                return []
            today = selected_today

        day_data = brand_data[today]
        campaign_type = (
            day_data.get(self.CAMPAIGN_TYPE, {})
            or day_data.get("mercado", {})
            or day_data.get("minuto", {})
        )
        campaigns = []
        seen = set()
        for city in TARGET_CITIES:
            camps = campaign_type.get(city, [])
            for c in camps:
                link = c.get("link", "")
                if link and link not in seen:
                    seen.add(link)
                    campaigns.append(
                        {
                            "codigo": c.get("codigo_campanha", ""),
                            "link": link,
                            "city": city,
                        }
                    )
        return campaigns

    def _fetch_page_texts(self, campaign_link: str) -> list[str]:
        base = campaign_link.rstrip("/")
        if base.endswith("index.html"):
            base = base[: -len("index.html")]
        base = base.rstrip("/")
        book_url = f"{base}/files/search/book_config.js"
        try:
            resp = self._http.get(book_url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.debug("book_config.js error: %s", e)
            return []

        m = re.search(r"var\s+textForPages\s*=\s*(\[.*?\])\s*;", resp.text, re.DOTALL)
        if not m:
            return []
        try:
            pages = json.loads(m.group(1))
            return [p for p in pages if isinstance(p, str) and p.strip()]
        except json.JSONDecodeError:
            return []

    @staticmethod
    def _clean_product_text(text: str) -> str:
        text = HEADER_CLEANUP.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = text.strip(".,;:- ")
        return text

    @staticmethod
    def _extract_validity(text: str) -> str:
        m = VALIDITY_DATE_RE.search(text)
        if m:
            return m.group(0)
        return ""

    @staticmethod
    def _is_valid_product(name: str) -> bool:
        if len(name) < 4:
            return False
        words = set(name.lower().split())
        stop_ratio = len(words & STOP_WORDS) / len(words) if words else 1
        return stop_ratio < 0.6

    @staticmethod
    def _parse_continuous_text(page_text: str) -> list[dict]:
        parts = PRICE_RE.split(page_text)
        products = []
        last_valid_name = ""
        validity = ""

        for i in range(0, len(parts) - 1, 2):
            raw_name = parts[i].strip()
            price_str = parts[i + 1].strip()
            price_str = price_str.replace(".", "").replace(",", ".")
            try:
                price = float(price_str)
            except ValueError:
                continue

            cleaned = ExtraFlyerScraper._clean_product_text(raw_name)
            if not cleaned:
                if last_valid_name:
                    continue
                continue

            if ExtraFlyerScraper._is_valid_product(cleaned):
                if not validity:
                    validity = ExtraFlyerScraper._extract_validity(page_text)
                unit = _extract_unit(cleaned)
                products.append(
                    {
                        "product": cleaned,
                        "price": price,
                        "unit": unit,
                        "validity_raw": validity,
                        "brand": "",
                    }
                )
                last_valid_name = cleaned

        return products

    def run(self, ingredients: list[dict] | None = None) -> list[dict]:
        data = self._fetch_campanhas()
        if not data:
            return []

        campaigns = self._get_campaign_links(data)
        if not campaigns:
            logger.info("[%s] No campaigns today", self.store_name)
            return []

        all_products = []
        for camp in campaigns:
            pages = self._fetch_page_texts(camp["link"])
            if not pages:
                continue

            products = []
            for page in pages:
                products.extend(self._parse_continuous_text(page))

            for p in products:
                p["source_url"] = camp["link"]

            logger.info("[%s] %s/%s: %d products", self.store_name, camp["codigo"], camp["city"], len(products))
            all_products.extend(products)

        return all_products
