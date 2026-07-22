"""Tenda Atacado catalog scraper — pega categorias e produtos direto do site.

Estrategia:
1. Le homepage e extrai catalogo de departamentos via __NEXT_DATA__.
2. Para cada categoria alvo (mercearia, bomboniere, laticinios, etc.):
   a. Lista de URLs de produto via regex em '/produto/<slug>'.
   b. Para cada produto, le a pagina de detalhe e extrai **Schema.org**
      markup (itemProp="price", itemProp="brand", itemProp="name") — que
      esta 100% presente no HTML SSR (testado).

Vantagens:
- Sem Playwright (rapido, baixo custo).
- Sem OCR (rapido, confiavel).
- Capta preco real (price) + marca + nome canonico.

Categorias que cobrem nossos ingredientes:
  - mercearia (acucar, arroz, leite em po, cafe, etc.)
  - bomboniere (chocolates, granulados, gotas)
  - frios-e-laticinios (manteiga, leite condensado, creme de leite)
  - paes-e-bolos (fermento, farinha)
  - higiene (baunilha, essencias)
"""
from __future__ import annotations

import json
import re

import httpx

from services.logger import logger
from services.scraper_health import record_failure, record_success
from services.url_guard import guard_url

BASE = "https://www.tendaatacado.com.br"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Cache-Control": "no-cache",
}

# Conexão reutilizável: limite de 8 conexões paralelas + keepalive.
_http_client: httpx.Client | None = None


def _client() -> httpx.Client:
    """Reutiliza um Client HTTP para evitar reconexão a cada request."""
    global _http_client
    if _http_client is None:
        limits = httpx.Limits(max_keepalive_connections=8, max_connections=12)
        _http_client = httpx.Client(
            headers=HEADERS, timeout=30.0, follow_redirects=True, limits=limits
        )
    return _http_client


def _http_get(url: str, timeout: float = 30.0) -> str | None:
    safe = guard_url(url)
    if not safe:
        return None
    try:
        r = _client().get(safe, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception as exc:
        logger.debug("[tenda_site] download fail %s: %s", url, exc)
        return None

# Coverage alinhada com o matcher do projeto.
# slug -> (
#   url-path,
#   departamento,
#   opcional: lista de sub-slugs que casam (se vazia, pega o slug direto)
# )
TARGET_DEPARTMENTS = {
    "bomboniere",
    "mercearia",
    "frios-e-laticinios",
    "paes-e-bolos",
    "doces-e-sobremesas",
    "cafe",
    "chocolate-em-po",
    "leite-em-po",
    "leites",
    "acucar-e-adocantes",
    "arroz",
    "farinhas",
    "acai",
    "chocolates",
    "confeitos",
    "coberturas-cremes-e-recheios",
    "leite-condensado",
    "manteiga",
    "creme-de-leite",
    "fermento",
    "biscoitos-torradas-e-salgadinhos",
}


def _flatten_categories(items: list[dict]) -> list[str]:
    """Pega todos os 'link' das categorias (recursivamente)."""
    out: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        link = (it.get("link") or "").strip()
        if link and it.get("hasProducts"):
            out.append(link)
        if it.get("children"):
            out.extend(_flatten_categories(it["children"]))
    return out


def _extract_next_data(html: str) -> dict | None:
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return None


def _list_product_slugs(html: str) -> list[str]:
    """Extrai URLs de produtos (slugs) de uma pagina de categoria."""
    return list({m.group(1) for m in re.finditer(r"href=\"(/produto/[^\"]+)\"", html)})


_PRODUCT_NAME_RE = re.compile(r'itemProp="name"\s+content="([^"]+)"')
_PRODUCT_PRICE_RE = re.compile(r'itemProp="price"\s+content="([\d.]+)"')
_PRODUCT_BRAND_RE = re.compile(
    r'itemProp="brand"[^>]*>.*?itemProp="name"\s+content="([^"]+)"',
    re.DOTALL,
)
_PRODUCT_BRAND_FB_RE = re.compile(r'<meta property="product:brand"\s+content="([^"]+)"/>')


def _extract_product_from_detail(html: str) -> dict | None:
    """Extrai nome, preco e marca de uma pagina de detalhe via Schema.org."""
    n = _PRODUCT_NAME_RE.search(html)
    p = _PRODUCT_PRICE_RE.search(html)
    if not n or not p:
        return None
    name = n.group(1)
    try:
        price = float(p.group(1))
    except ValueError:
        return None
    if price < 0.10:
        return None
    b = _PRODUCT_BRAND_RE.search(html)
    brand = b.group(1) if b else ""
    if not brand:
        b2 = _PRODUCT_BRAND_FB_RE.search(html)
        brand = b2.group(1) if b2 else ""
    return {"name": name, "price": price, "brand": brand}


def _categories_from_home() -> list[str]:
    """Pega lista de slugs de categorias do catalogo."""
    html = _http_get(BASE)
    if not html:
        return []
    nd = _extract_next_data(html)
    if not nd:
        return []
    items = nd.get("props", {}).get("pageProps", {}).get("items", [])
    if not isinstance(items, list):
        return []
    all_slugs = _flatten_categories(items)
    return [s for s in all_slugs if s in TARGET_DEPARTMENTS]


def _products_for_category(slug: str, page: int = 1) -> list[dict]:
    """Coleta produtos de uma pagina (page=N) de uma categoria.

    Downloads dos detalhes sao paralelos (ThreadPoolExecutor) para evitar
    custo serial de ~12-15 requests/pagina.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    url = f"{BASE}/{slug}?page={page}" if page > 1 else f"{BASE}/{slug}"
    html = _http_get(url)
    if not html:
        return []
    slugs = [sl for sl in _list_product_slugs(html) if sl.startswith("/produto/")]
    if not slugs:
        return []

    out: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_fetch_and_extract, sl, slug): sl for sl in slugs}
        for fut in as_completed(futures):
            prod = fut.result()
            if prod:
                out.append(prod)
    return out


def _fetch_and_extract(slug: str, category: str) -> dict | None:
    """Helper: baixa detalhe e extrai Schema.org."""
    detail_html = _http_get(BASE + slug)
    if not detail_html:
        return None
    prod = _extract_product_from_detail(detail_html)
    if prod:
        prod["slug"] = slug
        prod["category"] = category
        prod["source"] = "tenda_site"
    return prod


def _total_pages(slug: str) -> int:
    """Detecta quantas paginas uma categoria tem.

    Estrategia: conta o numero de links `/produto/` na primeira pagina
    (proxy de items_per_page ~= 12-17), divide o total conhecido
    (countProducts) e arredonda pra cima.
    """
    html = _http_get(f"{BASE}/{slug}")
    if not html:
        return 1
    nd = _extract_next_data(html)
    if not nd:
        return 1
    cat = nd.get("props", {}).get("pageProps", {}).get("category", {})
    total = cat.get("countProducts") if isinstance(cat, dict) else None
    if not isinstance(total, int) or total <= 0:
        return 1
    slugs_in_page = len(_list_product_slugs(html))
    if slugs_in_page <= 0:
        return 1
    pages = (total + slugs_in_page - 1) // slugs_in_page
    return min(pages, 20)  # cap de segurança (evita loops infinitos)


def scrape_store(store_name: str) -> list[dict]:
    """Ponto de entrada principal — pega catalogo + produtos.

    Retorna lista de dicts normalizados no formato do pipeline:
        {"product": str, "price": float, "unit": "", "brand": str, ...}

    Performance: categorias sao varridas em paralelo (ate 4 workers) com
    cada categoria respectando seu rate-limit interno (6 concurrent detail).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    try:
        cat_slugs = _categories_from_home()
        if not cat_slugs:
            logger.info("[tenda_site] nenhum departamento relevante encontrado")
            record_failure(store_name, reason="no relevant departments", attempted_by="tenda_site_scraper")
            return []

        logger.info("[tenda_site] encontrados %d departamentos alvo: %s", len(cat_slugs), cat_slugs)

        all_products: list[dict] = []
        seen: set[str] = set()

        def _harvest(slug: str) -> list[dict]:
            """Coleta produtos de uma categoria (todas as paginas)."""
            pages = _total_pages(slug)
            out: list[dict] = []
            for p in range(1, pages + 1):
                out.extend(_products_for_category(slug, page=p))
            return out

        # Paraleliza categorias (4 simultaneas), sequencial por pagina dentro
        # de cada categoria.
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = {ex.submit(_harvest, slug): slug for slug in cat_slugs}
            for fut in as_completed(futures):
                slug = futures[fut]
                try:
                    prods = fut.result()
                except Exception as exc:
                    logger.warning("[tenda_site] cat %s: %s", slug, exc)
                    continue
                added = 0
                for prod in prods:
                    key = f"{prod['name']}::{prod['price']}"
                    if key in seen:
                        continue
                    seen.add(key)
                    all_products.append(prod)
                    added += 1
                logger.info(
                    "[tenda_site] cat %s: %d produtos (%d unicos)",
                    slug, len(prods), added,
                )

        if all_products:
            record_success(
                store_name,
                items_found=len(all_products),
                attempted_by="tenda_site_scraper",
            )
            return [
                {
                    "product": p["name"],
                    "price": p["price"],
                    "unit": "",
                    "brand": p.get("brand", ""),
                    "category": p.get("category", ""),
                    "source": "tenda_site",
                    "store_name": store_name,
                }
                for p in all_products
            ]
        record_failure(
            store_name,
            reason="no products extracted from site",
            attempted_by="tenda_site_scraper",
        )
        return []
    except Exception as exc:
        logger.error("[tenda_site] run error: %s", exc)
        record_failure(
            store_name,
            reason=str(exc),
            attempted_by="tenda_site_scraper",
        )
        return []


if __name__ == "__main__":
    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "Tenda Atacado"
    prods = scrape_store(name)
    print(f"FOUND: {len(prods)} products")
    for p in prods[:15]:
        print(f"  - {p['product'][:60]:60s} R$ {p['price']:7.2f}  ({p.get('brand','')[:15]:15s}) [{p.get('category','')[:25]}]")
