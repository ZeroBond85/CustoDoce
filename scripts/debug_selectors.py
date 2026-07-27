#!/usr/bin/env python3
"""Debug selectors against real store websites.

Uso:
    python scripts/debug_selectors.py "<Store Name>" [--search <term>]
    python scripts/debug_selectors.py --list-stores
    python scripts/debug_selectors.py --all [--search <term>]

Carrega stores.yaml + selectors.yaml, fetches HTML real da loja,
e testa cada variante de selector reportando matches encontrados.

Exit code: 0 se pelo menos um selector encontrar produtos, 1 caso contrario.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

DEFAULT_TIMEOUT = httpx.Timeout(connect=15.0, read=30.0, pool=10.0, write=10.0)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_stores() -> list[dict]:
    raw = load_yaml(CONFIG_DIR / "stores.yaml")
    return raw.get("stores", [])


def load_selectors() -> dict:
    raw = load_yaml(CONFIG_DIR / "selectors.yaml")
    return raw


def resolve_selectors(store: dict, selectors_db: dict) -> dict:
    """Resolve selectors for a store: store-specific > type variant > defaults."""
    store_selectors = store.get("selectors") or {}
    store_type = store.get("type", "")
    variant = selectors_db.get(store_type) or {}
    defaults = selectors_db.get("defaults") or {}

    merged = {}
    for key in ("product_card", "product_name", "product_price", "product_old_price", "product_brand", "product_validity"):
        merged[key] = (
            store_selectors.get(key)
            or variant.get(key)
            or defaults.get(key)
            or []
        )
    return merged


def fetch_html(url: str) -> str | None:
    try:
        resp = httpx.get(url, headers={"User-Agent": UA}, timeout=DEFAULT_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  [ERRO] Falha ao fetch {url}: {e}")
        return None


def test_selectors(html: str, selectors: dict) -> dict:
    """Test CSS selectors against HTML using selectolax (or lxml fallback)."""
    results = {}
    try:
        from selectolax.parser import HTMLParser
        parser = HTMLParser(html)
        use_selectolax = True
    except ImportError:
        from lxml import html as lh
        parser = lh.fromstring(html)
        use_selectolax = False

    for key, selector_list in selectors.items():
        if not selector_list:
            results[key] = {"selectors_tested": 0, "total_matches": 0, "winners": []}
            continue
        best_count = 0
        best_selector = None
        details = []
        for sel in selector_list:
            try:
                if use_selectolax:
                    nodes = parser.css(sel)
                    count = len(nodes)
                    samples = []
                    for n in nodes[:3]:
                        text = n.text(strip=True) if hasattr(n, 'text') else ''
                        samples.append(text[:80] if text else '(empty)')
                else:
                    nodes = parser.cssselect(sel)
                    count = len(nodes)
                    samples = []
                    for n in nodes[:3]:
                        text = n.text_content().strip() if hasattr(n, 'text_content') else ''
                        samples.append(text[:80] if text else '(empty)')
            except Exception:
                count = 0
                samples = []
            details.append({"selector": sel, "matches": count, "samples": samples})
            if count > best_count:
                best_count = count
                best_selector = sel
        results[key] = {
            "selectors_tested": len(selector_list),
            "total_matches": best_count,
            "best_selector": best_selector,
            "details": details,
        }
    return results


def format_results(results: dict) -> str:
    lines = []
    for key, data in results.items():
        if data["selectors_tested"] == 0:
            lines.append(f"  {key}: (sem selectors configurados)")
            continue
        lines.append(f"  {key}: {data['total_matches']} matches (melhor: {data['best_selector']})")
        for d in data["details"]:
            marker = ">>" if d["selector"] == data["best_selector"] else "  "
            samples_str = f' ex: {d["samples"]}' if d["samples"] else ""
            lines.append(f"    {marker} {d['selector']}: {d['matches']} matches{samples_str}")
    return "\n".join(lines)


def debug_store(store: dict, search_term: str | None, selectors_db: dict) -> bool:
    name = store.get("name", "?")
    print(f"\n{'='*60}")
    print(f"Loja: {name}")
    print(f"  Tipo: {store.get('type', '?')} | Tier: {store.get('tier', '?')}")
    print(f"  URL: {store.get('base_url', '?')}")
    print(f"  Ativa: {store.get('is_active', False)}")

    selectors = resolve_selectors(store, selectors_db)
    print("\n  Selectors resolvidos:")
    for k, v in selectors.items():
        if v:
            print(f"    {k}: {v}")

    search_url_template = store.get("search_url") or ""
    browse_urls = store.get("browse_urls") or []

    if not search_term and not browse_urls:
        search_term = "leite condensado"

    urls_to_test = []
    if search_term:
        q = quote(search_term)
        url = search_url_template.format(query=q) if "{query}" in search_url_template else search_url_template
        if url:
            urls_to_test.append((f"search({search_term})", url))
    for i, bu in enumerate(browse_urls[:3]):
        full_url = bu if bu.startswith("http") else store.get("base_url", "") + bu
        urls_to_test.append((f"browse[{i}]", full_url))

    if not urls_to_test:
        urls_to_test.append(("base", store.get("base_url", "")))

    any_match = False
    for label, url in urls_to_test:
        if not url:
            continue
        print(f"\n  --- Fetching: {label} ---")
        print(f"  URL: {url}")
        html = fetch_html(url)
        if not html:
            continue
        print(f"  HTML: {len(html)} bytes")
        results = test_selectors(html, selectors)
        print(format_results(results))
        if results.get("product_card", {}).get("total_matches", 0) > 0:
            any_match = True
        time.sleep(0.5)

    return any_match


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    selectors_db = load_selectors()
    stores = load_stores()

    search_term = None
    if "--search" in args:
        idx = args.index("--search")
        search_term = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if "--list-stores" in args:
        print("Lojas disponiveis:")
        for s in stores:
            print(f"  {s.get('name', '?'):40s} tier={s.get('tier')} type={s.get('type')} active={s.get('is_active')}")
        sys.exit(0)

    if "--all" in args:
        successes = 0
        total = 0
        for store in stores:
            if not store.get("is_active", False):
                continue
            total += 1
            if debug_store(store, search_term, selectors_db):
                successes += 1
        print(f"\n{'='*60}")
        print(f"Resumo: {successes}/{total} lojas com pelo menos 1 selector de produto funcionando")
        sys.exit(0 if successes > 0 else 1)

    store_name = " ".join(args)
    store = None
    for s in stores:
        if s.get("name", "").lower() == store_name.lower():
            store = s
            break
    if not store:
        print(f"Loja '{store_name}' nao encontrada.")
        names = [s.get("name", "?") for s in stores if s.get("is_active")]
        print(f"Lojas ativas ({len(names)}):")
        for n in sorted(names):
            print(f"  {n}")
        sys.exit(1)

    ok = debug_store(store, search_term, selectors_db)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
