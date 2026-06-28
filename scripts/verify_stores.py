"""Verifica lojas website_catalog do stores.yaml + candidatas."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import yaml
import httpx
from selectolax.parser import HTMLParser
from scrapers.website_scraper import WebsiteScraper, DEFAULT_SELECTORS

CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_stores():
    with open(CONFIG_DIR / "stores.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    stores = data.get("stores", [])
    return [s for s in stores if s.get("is_active", True)]


def load_ingredients():
    with open(CONFIG_DIR / "ingredients.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("ingredients", [])


def test_store_reachability(store: dict):
    """Test if store URL is reachable and returns HTML."""
    base = store.get("base_url", "").rstrip("/")
    search_url_tpl = store.get("search_url") or f"{base}/busca?q={{query}}"

    result = {
        "name": store["name"],
        "tier": store.get("tier"),
        "type": store.get("type"),
        "scraper": store.get("scraper", ""),
        "city": store.get("city", store.get("cities", [""])[0]),
        "base_url": base,
        "search_url": search_url_tpl,
        "has_custom_selectors": bool(store.get("selectors")),
        "reachable": False,
        "status_code": 0,
        "html_size": 0,
        "products_found": 0,
        "products_with_price": 0,
        "sample_products": [],
        "error": None,
    }

    try:
        scraper = WebsiteScraper(store)
        html = scraper.fetch_search("leite condensado")
        if not html:
            result["error"] = "No HTML returned"
            return result

        result["reachable"] = True
        result["html_size"] = len(html)

        try:
            products = scraper.parse_results(html)
            result["products_found"] = len(products)
            result["products_with_price"] = sum(1 for p in products if p.get("price"))
            result["sample_products"] = products[:5]
        except Exception as e:
            tree = HTMLParser(html)
            cards = []
            for sel in DEFAULT_SELECTORS["product_card"]:
                cards = tree.css(sel)
                if cards:
                    break
            result["products_found"] = len(cards)
            result["error"] = f"Parse error: {e}"

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def test_new_candidate(name: str, base_url: str, search_url: str = None, city: str = ""):
    """Test a candidate store not yet in stores.yaml."""
    store = {
        "name": name,
        "base_url": base_url,
        "search_url": search_url or f"{base_url}/busca?q={{query}}",
        "tier": 2,
        "type": "website_catalog",
        "scraper": "website_scraper",
        "city": city,
        "selectors": {},
    }
    return test_store_reachability(store)


def main():
    stores = load_stores()

    # Filter website_catalog stores (both scraper types)
    website_stores = [
        s
        for s in stores
        if s.get("type") in ("website_catalog",) and s.get("scraper") in ("website_scraper", "carrefour_scraper")
    ]

    # Also test VTEX stores quickly
    vtex_stores = [s for s in stores if s.get("scraper") == "vtex_scraper"]

    print("=" * 70)
    print("VERIFICAÇÃO DE LOJAS - CustoDoce")
    print(f"Total website_catalog: {len(website_stores)}")
    print(f"Total VTEX: {len(vtex_stores)}")
    print("=" * 70)

    results = {}

    # Test website stores
    print("\n## WEBSITE CATALOG STORES ##")
    for store in website_stores:
        print(f"\n  ▶ {store['name']} ({store.get('city', '?')})")
        print(f"    URL: {store['base_url']}")
        result = test_store_reachability(store)
        results[store["name"]] = result

        status = (
            "✅" if result["reachable"] and result["products_with_price"] > 0 else "⚠️" if result["reachable"] else "❌"
        )
        print(
            f"    {status} HTTP {result['status_code']} | HTML: {result['html_size']}b | "
            f"Cards: {result['products_found']} | Preços: {result['products_with_price']}"
        )
        if result["error"]:
            print(f"    Erro: {result['error']}")
        if result["sample_products"]:
            for p in result["sample_products"]:
                print(f"      → {p['product'][:60]} | R$ {p.get('price', '?')} | {p.get('unit', '')}")
        time.sleep(0.5)

    # Test VTEX stores (quick reachability check)
    print("\n## VTEX STORES (alcance rápido) ##")
    client = httpx.Client(
        timeout=10.0,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
    )
    for store in vtex_stores:
        name = store["name"]
        api = store.get("api_endpoint", f"{store['base_url']}/api/catalog_system/pub/products/search")
        print(f"  ▶ {name}")
        try:
            resp = client.get(f"{api}?ft=leite+condensado&_q=leite+condensado")
            status = "✅" if resp.status_code == 200 else "⚠️" if resp.status_code < 500 else "❌"
            count = len(resp.json()) if resp.status_code == 200 else 0
            print(f"    {status} HTTP {resp.status_code} | {count} produtos")
        except Exception as e:
            print(f"    ❌ Erro: {str(e)[:80]}")
        time.sleep(0.3)

    # Test new candidates
    print("\n## CANDIDATAS NOVAS ##")
    candidates = [
        ("MM Santos", "https://mmsantos.com.br", None, "Santos"),
        ("Maria Chocolate", "https://www.mariachocolate.com.br", None, "Belo Horizonte"),
        ("Shopping do Confeiteiro", "https://www.shoppingdoconfeiteiro.com.br", None, "Brasília"),
        ("Mercadoce", "https://www.mercadoce.com", None, "Sorocaba"),
        ("Docerrano", "https://www.docerrano.com.br", None, "Sorocaba"),
        ("Confeitar", "https://amoconfeitar.com.br", None, "Curitiba"),
        ("Lô Confeiteira", "https://loconfeiteira.com.br", None, "? (online)"),
    ]
    for name, url, search_url, city in candidates:
        print(f"\n  ▶ {name} ({city})")
        print(f"    URL: {url}")
        try:
            result = test_new_candidate(name, url, search_url, city)
            status = (
                "✅"
                if result["reachable"] and result["products_with_price"] > 0
                else "⚠️"
                if result["reachable"]
                else "❌"
            )
            print(
                f"    {status} HTTP {result['status_code']} | HTML: {result['html_size']}b | "
                f"Produtos: {result['products_found']} | Preços: {result['products_with_price']}"
            )
            if result["error"]:
                print(f"    Erro: {result['error']}")
            if result["sample_products"]:
                for p in result["sample_products"]:
                    print(f"      → {p['product'][:60]} | R$ {p.get('price', '?')} | {p.get('unit', '')}")
        except Exception as e:
            print(f"    ❌ Falha: {str(e)[:100]}")
        time.sleep(0.5)

    # Summary
    print("\n" + "=" * 70)
    print("RESUMO")
    print("=" * 70)
    working = [k for k, v in results.items() if v["reachable"] and v["products_with_price"] > 0]
    reachable = [k for k, v in results.items() if v["reachable"]]
    failed = [k for k, v in results.items() if not v["reachable"]]
    print(f"\n✅ Funcionando (com preços): {len(working)}")
    for s in working:
        r = results[s]
        print(f"  - {s}: {r['products_with_price']} produtos com preço")
    print(f"\n⚠️  Acessível (sem preços detectados): {len(reachable) - len(working)}")
    for s in reachable:
        if s not in working:
            r = results[s]
            print(f"  - {s}: {r['products_found']} cards, {r['products_with_price']} com preço")
    print(f"\n❌ Inacessível: {len(failed)}")
    for s in failed:
        r = results[s]
        print(f"  - {s}: {r.get('error', 'unknown')}")


if __name__ == "__main__":
    main()
