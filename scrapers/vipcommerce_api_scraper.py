"""Scraper para lojas na plataforma VipCommerce (Spani, Rede Krill, ...).

VipCommerce expõe uma API JSON pública (após login anônimo de loja) muito mais
eficiente e estável que raspar o SPA Angular. Fluxo:

1. POST ``/org/{org}/auth/loja/login`` com ``key`` da loja → Bearer token.
2. GET  ``.../departamentos/arvore`` → árvore de departamentos.
3. Seleciona departamentos relevantes por palavra-chave (confeitaria).
4. Pagina ``.../departamentos/{id}/produtos?page=N`` até ``total_pages``
   (respeitando um teto ``max_pages_per_dept`` para o free tier).

O matcher downstream filtra os produtos para os ingredientes monitorados, então
o scraper devolve todos os produtos crus dos departamentos escolhidos.
"""

from __future__ import annotations

from urllib.parse import urlparse

from parsers.unit_extractor import extract_unit
from scrapers.base_web_scraper import BaseWebScraper
from services.logger import logger

DEFAULT_API_BASE = "https://services-beta.vipcommerce.com.br/api-admin/v1"

# Departamentos relevantes para os 23 ingredientes de confeitaria monitorados.
# Casamento por substring (case-insensitive) no nome do departamento — robusto
# entre lojas VipCommerce que nomeiam departamentos de forma parecida.
DEFAULT_DEPT_KEYWORDS = [
    "chocolate",
    "biscoito",
    "mercearia",
    "cereais",
    "farinac",
    "matinais",
    "sobremesa",
    "laticinio",
    "doce",
    "confeitaria",
]


class VipCommerceApiScraper(BaseWebScraper):
    # Scraper puramente HTTP (login + API JSON) com timeouts delimitados:
    # seguro rodar no processo pai (evita o spawn lento no Windows).
    safe_in_parent = True
    def __init__(self, store_config: dict):
        super().__init__(store_config)
        self.api_base = (store_config.get("vip_api_base") or DEFAULT_API_BASE).rstrip("/")
        self.domain = store_config.get("vip_domain") or self._host_from_base_url()
        self.org_id = str(store_config.get("vip_org_id", "")).strip()
        self.filial_id = str(store_config.get("vip_filial_id", "1")).strip()
        self.cd_id = str(store_config.get("vip_cd_id", "1")).strip()
        self.login_key = store_config.get("vip_login_key", "")
        self.login_username = store_config.get("vip_login_username", "loja")
        self.dept_keywords = [k.lower() for k in (store_config.get("vip_dept_keywords") or DEFAULT_DEPT_KEYWORDS)]
        self.max_pages_per_dept = int(store_config.get("vip_max_pages_per_dept", 15))
        self.max_pages_per_search = int(store_config.get("vip_max_pages_per_search", 3))
        # Modo de coleta: 'dept' (navega departamentos de confeitaria) ou
        # 'search' (busca direta pelos termos dos ingredientes monitorados).
        # 'search' é muito mais eficiente: devolve só produtos relevantes.
        self.mode = (store_config.get("vip_mode") or "dept").lower()
        # Filtro opcional de ingredientes: se informado (lista de canonical_name),
        # só esses ingredientes são buscados. Reduz drasticamente o volume de
        # requisições/upserts quando a loja só carrega um subconjunto (ex: Krill).
        self.search_ingredients = [str(x).strip().lower() for x in (store_config.get("vip_search_ingredients") or [])]
        self._token: str | None = None

    def _filter_ingredients(self, ingredients: list[dict]) -> list[dict]:
        if not self.search_ingredients:
            return ingredients
        wanted = set(self.search_ingredients)
        return [ing for ing in ingredients if (ing.get("canonical_name") or "").strip().lower() in wanted]

    def _host_from_base_url(self) -> str:
        host = urlparse(self.base_url).netloc or self.base_url
        return host.replace("www.", "")

    def _headers(self, with_auth: bool = True) -> dict:
        h = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "DomainKey": self.domain,
            "OrganizationId": self.org_id,
        }
        if with_auth and self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _loja_base(self) -> str:
        return (
            f"{self.api_base}/org/{self.org_id}/filial/{self.filial_id}"
            f"/centro_distribuicao/{self.cd_id}/loja"
        )

    def _dept_base(self) -> str:
        return f"{self._loja_base()}/classificacoes_mercadologicas/departamentos"

    def _login(self) -> bool:
        if not (self.org_id and self.login_key and self.domain):
            logger.error("[%s] VipCommerce: faltam vip_org_id/vip_login_key/vip_domain", self.name)
            return False
        url = f"{self.api_base}/org/{self.org_id}/auth/loja/login"
        body = {"domain": self.domain, "username": self.login_username, "key": self.login_key}
        try:
            resp = self._http.post(url, json=body, headers=self._headers(with_auth=False))
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("[%s] VipCommerce login falhou: %s", self.name, e)
            return False
        token = data.get("data") if isinstance(data, dict) else None
        if not token or not isinstance(token, str):
            logger.error("[%s] VipCommerce login sem token: %s", self.name, str(data)[:120])
            return False
        self._token = token
        return True

    def _select_departments(self) -> list[dict]:
        try:
            resp = self._http.get(f"{self._dept_base()}/arvore", headers=self._headers())
            resp.raise_for_status()
            tree = (resp.json() or {}).get("data") or []
        except Exception as e:
            logger.error("[%s] VipCommerce árvore de departamentos falhou: %s", self.name, e)
            return []
        selected = []
        for dep in tree:
            name = (dep.get("descricao") or "").lower()
            dep_id = dep.get("classificacao_mercadologica_id")
            if dep_id is not None and any(kw in name for kw in self.dept_keywords):
                selected.append({"id": dep_id, "descricao": dep.get("descricao")})
        logger.info("[%s] VipCommerce: %d departamentos selecionados: %s", self.name, len(selected),
                    ", ".join(d["descricao"] for d in selected))
        return selected

    def _fetch_dept_products(self, dep: dict) -> list[dict]:
        products: list[dict] = []
        page = 1
        total_pages = 1
        while page <= min(total_pages, self.max_pages_per_dept):
            url = f"{self._dept_base()}/{dep['id']}/produtos?page={page}"
            try:
                resp = self._http.get(url, headers=self._headers())
                resp.raise_for_status()
                payload = resp.json() or {}
            except Exception as e:
                logger.warning("[%s] VipCommerce dept %s page %d falhou: %s", self.name, dep["descricao"], page, e)
                break
            data = payload.get("data") or []
            for raw in data:
                if not isinstance(raw, dict):
                    continue
                parsed = self._parse_product(raw)
                if parsed:
                    products.append(parsed)
            paginator = payload.get("paginator") or {}
            total_pages = int(paginator.get("total_pages", 1) or 1)
            page += 1
            self._throttle()
        logger.info("[%s] VipCommerce dept %s: %d produtos", self.name, dep["descricao"], len(products))
        return products

    def _parse_product(self, raw: dict) -> dict | None:
        name = (raw.get("descricao") or "").strip()
        if not name:
            return None
        price = self._to_price(raw.get("preco"))
        if raw.get("em_oferta") and isinstance(raw.get("oferta"), dict):
            oferta_price = self._to_price(raw["oferta"].get("preco_oferta") or raw["oferta"].get("preco"))
            if oferta_price is not None:
                price = oferta_price
        if price is None:
            return None
        return {
            "product": name,
            "price": price,
            "unit": extract_unit(name) or (raw.get("unidade_sigla") or "").lower(),
            "validity_raw": "",
            "brand": "",
        }

    @staticmethod
    def _to_price(value) -> float | None:
        if value is None:
            return None
        try:
            price = float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return None
        return price if price > 0 else None

    def parse_products(self, raw_data) -> list[dict]:
        return []

    def run(self, ingredients: list[dict]) -> list[dict]:
        if not self._login():
            self.report_failure(reason="VipCommerce login falhou", items_found=0, products_matched=0)
            return []
        if self.mode == "search":
            all_products = self._run_search(self._filter_ingredients(ingredients))
        else:
            all_products = self._run_departments()
        if all_products:
            self.report_success(items_found=len(all_products), products_matched=0)
        else:
            self.report_failure(reason="0 produtos coletados da API VipCommerce", items_found=0, products_matched=0)
        return all_products

    def _run_departments(self) -> list[dict]:
        departments = self._select_departments()
        if not departments:
            return []
        all_products: list[dict] = []
        for dep in departments:
            all_products.extend(self._fetch_dept_products(dep))
        return all_products

    def _run_search(self, ingredients: list[dict]) -> list[dict]:
        # Termos únicos: ingredientes compartilham canonical/aliases, então
        # deduplicar evita N requisições redundantes (economiza tempo de
        # orçamento no free tier). O matcher downstream cobre todos os ingredientes.
        unique_terms: list[str] = []
        seen_terms: set[str] = set()
        for ing in ingredients:
            terms = list(ing.get("search_terms", []))
            if ing.get("canonical_name"):
                terms.append(ing["canonical_name"])
            terms.extend(ing.get("aliases", []))
            for term in terms:
                if term and term.lower() not in seen_terms:
                    seen_terms.add(term.lower())
                    unique_terms.append(term)
        all_products: list[dict] = []
        seen: set[str] = set()
        for term in unique_terms:
            for prod in self._fetch_search_products(term):
                key = prod["product"]
                if key not in seen:
                    seen.add(key)
                    all_products.append(prod)
            self._throttle()
        return all_products

    def _fetch_search_products(self, term: str) -> list[dict]:
        # Endpoint real descoberto em produção: /loja/buscas/produtos/termo/{termo}?page=N
        products: list[dict] = []
        term_url = term.replace(" ", "+")
        page = 1
        total_pages = 1
        while page <= min(total_pages, self.max_pages_per_search):
            url = (
                f"{self._loja_base()}/buscas/produtos/termo/{term_url}?page={page}"
            )
            try:
                resp = self._http.get(url, headers=self._headers())
                resp.raise_for_status()
                payload = resp.json() or {}
            except Exception as e:
                logger.warning("[%s] VipCommerce busca '%s' p%d falhou: %s | url=%s", self.name, term, page, e, url)
                break
            data = payload.get("data") or {}
            # Busca: produtos em data["produtos"] (lista). Departamento:
            # data é a própria lista de produtos.
            items = data.get("produtos") if isinstance(data, dict) else data
            if not isinstance(items, list):
                items = []
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                parsed = self._parse_product(raw)
                if parsed:
                    products.append(parsed)
            paginator = payload.get("paginator") or {}
            total_pages = int(paginator.get("total_pages", 1) or 1)
            page += 1
            self._throttle()
        if products:
            logger.info("[%s] VipCommerce busca '%s': %d produtos", self.name, term, len(products))
        return products
