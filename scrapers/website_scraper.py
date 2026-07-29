import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

from selectolax.parser import HTMLParser

from parsers.unit_extractor import extract_unit
from scrapers.base_web_scraper import BaseWebScraper, _retry_with_backoff
from services.logger import logger
from services.selector_resolver import resolve_selectors

_HAS_CURL_CFFI = False
try:
    from curl_cffi import requests as curl_requests
    _HAS_CURL_CFFI = True
except ImportError:
    curl_requests = None


class WebsiteScraper(BaseWebScraper):
    # Scraper HTTP (requests) com timeouts por-URL: seguro no processo pai
    # (evita o spawn lento/no Windows que degrada as requisições).
    safe_in_parent = True

    def __init__(self, store_config: dict):
        super().__init__(store_config)
        self.search_url = store_config.get("search_url") or f"{self.base_url}/busca?q={{query}}"
        self.selectors = resolve_selectors(store_config)
        self.browse_parallel = store_config.get("browse_parallel", False)
        # Teto de parede por URL de browse: evita que UMA url lenta/travada
        # (Cloudflare, WAF) segure o loop paralelo inteiro. Default 30s.
        self.browse_url_timeout = float(store_config.get("browse_url_timeout", 30))
        # Modo Shopify Storefront JSON API: algumas lojas (ex.: Chefon)
        # protegem as paginas HTML com Cloudflare (HTTP 429), CSS/JS static assets
        # e a propria rota /collections/<x>/products.json tambem — Cloudflare
        # bloqueia o fingerprint TLS do httpx (JA3). curl_cffi com
        # impersonate="chrome120" contorna o bloqueio via fingerprint do Chrome.
        self.shopify_json = bool(store_config.get("shopify_json", False))
        self.shopify_curl_cffi = bool(store_config.get("shopify_curl_cffi", False))
        if self.shopify_curl_cffi and not _HAS_CURL_CFFI:
            logger.warning("[%s] shopify_curl_cffi=true mas curl_cffi nao instalado — fallback httpx", self.name)
            self.shopify_curl_cffi = False
        self.shopify_collections = store_config.get("shopify_collections") or ["all"]
        self.shopify_page_limit = int(store_config.get("shopify_page_limit", 250))
        self.shopify_max_pages = int(store_config.get("shopify_max_pages", 40))
        self.shopify_curl_cffi_retries = int(store_config.get("shopify_curl_cffi_retries", 4))
        self.shopify_curl_cffi_base_delay = float(store_config.get("shopify_curl_cffi_base_delay", 15.0))
        self.shopify_curl_cffi_max_delay = float(store_config.get("shopify_curl_cffi_max_delay", 120.0))
        self.shopify_playwright_fallback = bool(store_config.get("shopify_playwright_fallback", False))

    def fetch_search(self, query: str) -> str | None:
        url = self.search_url.format(query=quote(query))
        try:
            resp = self._http.get(url)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.error("[%s] Error fetching '%s': %s", self.name, url, e)
            return None

    @_retry_with_backoff(max_retries=2, base_delay=2.0, max_delay=10.0)
    def _fetch_browse_raw(self, url: str) -> str | None:
        resp = self._http.get(url)
        resp.raise_for_status()
        return resp.text

    def fetch_browse(self, url: str) -> str | None:
        """Busca com teto de parede por URL (anti-travamento em Cloudflare/WAF)."""
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        if self.browse_url_timeout and self.browse_url_timeout > 0:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(self._fetch_browse_raw, url)
                try:
                    return fut.result(timeout=self.browse_url_timeout)
                except FuturesTimeout:
                    logger.warning(
                        "[%s] browse %s estourou teto de %ds (Cloudflare/WAF?) — ignorado",
                        self.name, url, int(self.browse_url_timeout),
                    )
                    return None
        return self._fetch_browse_raw(url)

    def run(self, ingredients: list[dict]) -> list[dict]:
        """Coleta via Shopify JSON API quando ``shopify_json`` esta ativo,
        via browse_urls (departamentos) quando configurado, ou 1 busca por
        ingrediente (padrao).
        """
        if self.shopify_json:
            return self._run_shopify_json()

        browse_urls = self.store.get("browse_urls") or []
        if not browse_urls:
            return super().run(ingredients)

        import time as _time
        start_ts = _time.time()
        logger.info("[%s] browse_urls mode: %d paginas de departamento", self.name, len(browse_urls))
        all_entries: list[dict] = []

        if self.browse_parallel:
            with ThreadPoolExecutor(max_workers=min(4, len(browse_urls))) as ex:
                url_map = {ex.submit(self.fetch_browse, url): url for url in browse_urls}
                for fut in as_completed(url_map):
                    url = url_map[fut]
                    html = fut.result()
                    if not html:
                        logger.warning("[%s] browse %s falhou (0 bytes)", self.name, url)
                        continue
                    found = self.parse_products(html)
                    logger.info("[%s] browse %s -> %d produtos", self.name, url, len(found))
                    all_entries.extend(found)
        else:
            for i, url in enumerate(browse_urls, 1):
                html = self.fetch_browse(url)
                self._throttle()
                if not html:
                    logger.warning("[%s] browse %d/%d vazio: %s", self.name, i, len(browse_urls), url)
                    continue
                found = self.parse_products(html)
                logger.info("[%s] browse %d/%d: %d produtos (%.1fs)", self.name, i, len(browse_urls), len(found), _time.time() - start_ts)
                all_entries.extend(found)
        logger.info("[%s] browse total: %d produtos em %.1fs", self.name, len(all_entries), _time.time() - start_ts)
        return all_entries

    def _run_shopify_json(self) -> list[dict]:
        """Coleta TODOS os produtos via Shopify Storefront JSON API.

        Endpoint publico ``/collections/<col>/products.json?limit=250&page=N``.
        Usa curl_cffi com Chrome120 impersonation (bypass TLS fingerprint).
        Quando ``shopify_playwright_fallback`` esta ativo, tenta Playwright
        como fallback se o curl_cffi falhar com 429 (padrao: desligado,
        pois Playwright tambem e bloqueado por IP de datacenter CI).
        """
        import time as _time

        start_ts = _time.time()
        all_entries: list[dict] = []
        use_playwright = False
        _pw_ctx = None

        for collection in self.shopify_collections:
            page = 1
            while page <= self.shopify_max_pages:
                url = f"{self.base_url}/collections/{collection}/products.json"
                params = {"limit": self.shopify_page_limit, "page": page}

                try:
                    if use_playwright:
                        resp = self._fetch_shopify_page_via_playwright(url, params, _pw_ctx)
                    else:
                        resp = self._fetch_shopify_page(url, page)
                except Exception as e:
                    logger.error("[%s] Erro Shopify collection=%s page=%d: %s", self.name, collection, page, e)
                    if (
                        not use_playwright
                        and self.shopify_playwright_fallback
                        and self._is_429_error(e)
                    ):
                        logger.warning("[%s] curl_cffi bloqueado (429) — tentando Playwright...", self.name)
                        pw_resp, _pw_ctx = self._init_playwright_for_shopify(url)
                        if pw_resp is not None:
                            use_playwright = True
                            resp = pw_resp
                        else:
                            break
                    else:
                        break

                if resp is None:
                    break
                prods = resp.get("products", [])
                if not prods:
                    break
                for p in prods:
                    entry = self._parse_shopify_product(p)
                    if entry:
                        all_entries.append(entry)
                logger.info(
                    "[%s] Shopify %s page %d: %d produtos (accum %d, %.1fs)",
                    self.name, collection, page, len(prods), len(all_entries), _time.time() - start_ts,
                )
                if len(prods) < self.shopify_page_limit:
                    break
                page += 1
                self._throttle()

        if _pw_ctx:
            _pw_ctx[0].close()

        logger.info(
            "[%s] Shopify coleta total: %d produtos em %.1fs", self.name, len(all_entries), _time.time() - start_ts
        )
        return all_entries

    def _is_429_error(self, exc: Exception) -> bool:
        """Verifica se a excecao corresponde a HTTP 429 (curl_cffi ou httpx)."""
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return status == 429 or "429" in str(exc)

    def _init_playwright_for_shopify(self, url: str) -> tuple[dict | None, tuple | None]:
        """Inicializa Playwright com Chromium e retorna a primeira pagina + context tuple.

        Retorna (response_json, (browser, context, playwright_instance)) ou (None, None).
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("[%s] playwright nao instalado — sem bypass Cloudflare", self.name)
            return None, None

        params = {"limit": self.shopify_page_limit, "page": 1}
        query = "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{url}?{query}"
        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="pt-BR",
            )
            page_obj = ctx.new_page()
            response = page_obj.goto(full_url, wait_until="networkidle", timeout=60000)
            if response and response.ok:
                data = response.json()
                logger.info("[%s] Playwright iniciado — OK page 1 (%d produtos)", self.name, len(data.get("products", [])))
                ctx_tuple = (browser, pw)
                return data, ctx_tuple
            logger.error("[%s] Playwright HTTP %s na inicializacao", self.name, response.status if response else "???")
            browser.close()
            pw.stop()
            return None, None
        except Exception as e:
            logger.error("[%s] Playwright init falhou: %s", self.name, e)
            return None, None

    def _fetch_shopify_page(self, url: str, page: int) -> dict | None:
        """Busca 1 pagina via curl_cffi com retry + backoff exponencial.

        Parametros de retry sao configurados via stores.yaml:
          shopify_curl_cffi_retries (default 4)
          shopify_curl_cffi_base_delay (default 15s)
          shopify_curl_cffi_max_delay (default 120s)

        Quando curl_cffi esta ativo e todas as tentativas falharem com 429,
        retorna None sem tentar httpx (que tambem seria bloqueado por
        Cloudflare). Quando curl_cffi nao esta configurado/disponivel, usa
        httpx como fallback (compativel com testes unitarios).
        """
        params = {"limit": self.shopify_page_limit, "page": page}

        if self.shopify_curl_cffi and _HAS_CURL_CFFI:
            for attempt in range(self.shopify_curl_cffi_retries):
                try:
                    resp = curl_requests.get(
                        url, params=params, timeout=30, impersonate="chrome120",
                    )
                    resp.raise_for_status()
                    return resp.json()
                except Exception as e:
                    status = getattr(getattr(e, "response", None), "status_code", None)
                    if status == 429:
                        if attempt < self.shopify_curl_cffi_retries - 1:
                            delay = min(
                                self.shopify_curl_cffi_base_delay * (2**attempt),
                                self.shopify_curl_cffi_max_delay,
                            )
                            logger.warning(
                                "[%s] curl_cffi 429 page %d (attempt %d/%d) — retry %.0fs",
                                self.name, page, attempt + 1, self.shopify_curl_cffi_retries, delay,
                            )
                            time.sleep(delay)
                        else:
                            logger.error(
                                "[%s] curl_cffi page %d esgotou %d tentativas com 429 — retornando None",
                                self.name, page, self.shopify_curl_cffi_retries,
                            )
                            return None
                    else:
                        logger.error(
                            "[%s] curl_cffi page %d erro nao-recuperavel: %s",
                            self.name, page, e,
                        )
                        return None

        # Fallback httpx: usado quando curl_cffi nao esta configurado ou
        # nao instalado (ex.: testes unitarios que mockam self._http).
        try:
            resp = self._http.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("[%s] HTTP page %d falhou: %s", self.name, page, e)
            return None

    def _fetch_shopify_page_via_playwright(self, url: str, params: dict, ctx_tuple: tuple | None = None) -> dict | None:
        """Busca 1 pagina via Playwright reusando browser ja aberto.

        ``ctx_tuple`` = (browser, playwright_instance) retornado por
        ``_init_playwright_for_shopify()``. Se None, abre/fecha browser
        a cada chamada (ineficiente, usado apenas em fallback individual).
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return None

        query = "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{url}?{query}"

        if ctx_tuple:
            browser, pw = ctx_tuple
            page_obj = browser.new_page()
            try:
                response = page_obj.goto(full_url, wait_until="networkidle", timeout=60000)
                if response and response.ok:
                    data = response.json()
                    page_obj.close()
                    return data
                page_obj.close()
                return None
            except Exception as e:
                logger.error("[%s] Playwright page %s erro: %s", self.name, params.get("page", "?"), e)
                page_obj.close()
                return None
        else:
            # Fallback: abre/fecha browser por chamada
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page_obj = browser.new_page()
                    response = page_obj.goto(full_url, wait_until="networkidle", timeout=60000)
                    if response and response.ok:
                        return response.json()
                    return None
            except Exception as e:
                logger.error("[%s] Playwright avulso falhou: %s", self.name, e)
                return None

    def _parse_shopify_product(self, p: dict) -> dict | None:
        """Converte 1 produto Shopify no contrato padrao (product/price/unit/brand)."""
        title = (p.get("title") or "").strip()
        variants = p.get("variants") or []
        if not title or not variants:
            return None
        # Usa a primeira variante disponivel (com estoque) ou a primeira qualquer.
        chosen = None
        for v in variants:
            if v.get("available", True):
                chosen = v
                break
        if chosen is None:
            chosen = variants[0]
        price = chosen.get("price")
        if price is None:
            return None
        try:
            price = float(price)
        except (TypeError, ValueError):
            return None
        if price <= 0:
            return None
        # Shopify nao expoe validade; unit vem do nome.
        unit = extract_unit(title)
        vendor = (p.get("vendor") or "").strip()
        return {
            "product": title,
            "price": price,
            "unit": unit,
            "validity_raw": "",
            "brand": vendor,
        }

    def parse_products(self, html: str) -> list[dict]:
        products = self._parse_jsonld(html)
        if products:
            return products

        tree = HTMLParser(html)
        cards = self._find_nodes(tree)
        products = []

        for card in cards:
            name = self._extract_name(card)
            if not name:
                continue
            price = self._extract_price(card)
            if price is None:
                continue
            unit = extract_unit(name)
            validity = self._extract_validity(card)
            brand = self._extract_brand(card)
            products.append(
                {
                    "product": name.strip(),
                    "price": price,
                    "unit": unit,
                    "validity_raw": validity,
                    "brand": brand,
                }
            )

        return products

    def _parse_jsonld(self, html: str) -> list[dict]:
        """Extrai produtos de JSON-LD embedado (VTEX IO / Schema.org)."""
        products: list[dict] = []
        m = re.findall(r'<script\s+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
        for block in m:
            try:
                data = json.loads(block.strip())
                items = []
                if data.get("@type") == "ItemList":
                    items = data.get("itemListElement", [])
                for entry in items:
                    item = entry.get("item", {})
                    if not item.get("name"):
                        continue
                    offers = item.get("offers", {})
                    price = offers.get("lowPrice") or offers.get("price") or 0
                    if price <= 0:
                        continue
                    name = item["name"].strip()
                    products.append({
                        "product": name,
                        "price": float(price),
                        "unit": extract_unit(name),
                        "validity_raw": "",
                        "brand": "",
                    })
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return products

    def _find_nodes(self, tree: HTMLParser) -> list:
        for selector in self.selectors["product_card"]:
            nodes = tree.css(selector)
            if nodes:
                return nodes
        return []

    def _extract_name(self, node) -> str | None:
        for selector in self.selectors["product_name"]:
            found = node.css(selector)
            if found:
                text = found[0].text().strip()
                if text:
                    return text
        text = node.text().strip()
        return text if text else None

    def _extract_price(self, node) -> float | None:
        for selector in self.selectors["product_price"]:
            found = node.css(selector)
            if found:
                text = found[0].text().strip()
                price = self._parse_price(text)
                if price is not None:
                    return price
        return None

    @staticmethod
    def _parse_price(text: str) -> float | None:
        m = re.search(r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)", text)
        if m:
            raw = m.group(1).replace(".", "").replace(",", ".")
            try:
                return float(raw)
            except ValueError:
                pass
        return None

    def _extract_brand(self, node) -> str:
        for selector in self.selectors.get("product_brand", []):
            found = node.css(selector)
            if found:
                text = found[0].text().strip()
                if text:
                    return text
        return ""

    def _extract_validity(self, node) -> str:
        for selector in self.selectors.get("product_validity", []):
            found = node.css(selector)
            if found:
                text = found[0].text().strip()
                if text:
                    return text
        return ""
