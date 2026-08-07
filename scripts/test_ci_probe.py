"""Sonda anti-bot: diagnostica bloqueios Tiendeo/Carrefour no runner do GitHub.

Roda uma matriz de metodos (httpx, requests, curl_cffi com varios impersonates,
cookie warmup, mobile UA, GraphQL, VTEX API, Playwright) contra URLs dos dois
sites e classifica cada resposta: 200 real / cloudflare challenge / 403 / 429.

Uso:
    python scripts/test_ci_probe.py                 # tabela no stdout
    python scripts/test_ci_probe.py --json data/probe_results.json
    python scripts/test_ci_probe.py --playwright    # inclui Playwright
    python scripts/test_ci_probe.py <url-extra>     # testa URLs extras com httpx
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, ".")

TIENDEO_BASE = "https://www.tiendeo.com.br"
CARREFOUR_BASE = "https://mercado.carrefour.com.br"

UA_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)

BROWSER_HEADERS = {
    "User-Agent": UA_CHROME,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "max-age=0",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

IMPERSONATES = ["chrome", "chrome124", "safari17_0", "edge99", "firefox133"]

CARREFOUR_GRAPHQL_QUERY = """
query SearchProducts($term: String!, $first: Int!) {
    search(term: $term, first: $first) {
        products {
            edges {
                node {
                    id
                    name
                    priceRange { minVariantPrice { amount } }
                    brand { name }
                }
            }
        }
    }
}
"""

# Marcadores FORTES = challenge ativo (Cloudflare está bloqueando de verdade)
CF_CHALLENGE_STRONG = [
    "cf-chl-",
    "cf_chl_",
    "challenge-form",
    "challenge-form-wrapper",
    "Attention Required",
    "Just a moment",
    "cf-mitigated",
    "Managed Challenge",
    "Enable JavaScript and cookies",
    "verifying you are human",
    "cf_cwv",
    "turnstile",
    "cdn-cgi/challenge-platform/h/b",
]
# Marcadores FRACOS = Cloudflare presente no HTML, mas pode ser página normal
CF_PRESENT_WEAK = ["challenge-platform", "cf-ray", "__cf_bm", "cdn-cgi/challenge-platform", "cf_chl_opt"]

GENERIC_403_MARKERS = [
    "forbidden",
    "acesso negado",
    "access denied",
    "not allowed",
    "403",
]

GENERIC_403_MARKERS = [
    "forbidden",
    "acesso negado",
    "access denied",
    "not allowed",
    "403",
]

# Resultado por teste: (metodo, url, status, tipo, tamanho, marcador, tempo_s)
ProbeResult = dict


def classify(status: int | None, body: str, headers: dict) -> tuple[str, str]:
    """Classifica a resposta: (tipo, marcador_detectado)."""
    low = (body or "").lower()
    header_low = " ".join(f"{k}={v}" for k, v in headers.items()).lower()
    haystack = low + " " + header_low

    strong = [m for m in CF_CHALLENGE_STRONG if m.lower() in haystack]
    weak = [m for m in CF_PRESENT_WEAK if m.lower() in haystack]

    if strong:
        if status == 200:
            return "cloudflare_challenge_200", strong[0]
        if status == 403:
            return "cloudflare_403", strong[0]
        if status == 429:
            return "cloudflare_429", strong[0]
        return "cloudflare_challenge", strong[0]

    if status == 200:
        if len(body) < 2000:
            return "200_vazio", f"len={len(body)}"
        if weak:
            return "200_real_cf_presente", f"{weak[0]} len={len(body)}"
        return "200_real", f"len={len(body)}"

    if weak and status in (403, 429):
        return f"cf_presente_{status}", weak[0]
    if status == 403:
        return "403_generico", next((m for m in GENERIC_403_MARKERS if m in low), "sem-marcador")
    if status == 429:
        return "429", "rate-limit"
    if status == 503:
        return "503", "service-unavailable"
    err = headers.get("err")
    if err:
        return f"http_{status}", err
    return f"http_{status}", ""


def _truncate(body: str, n: int = 300) -> str:
    text = re.sub(r"<[^>]+>", " ", body or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n]


def _summary(result: ProbeResult) -> str:
    kind = result["tipo"]
    ok = kind in ("200_real", "200_real_cf_presente", "cloudflare_challenge_200")
    mark = "OK " if ok else "XX "
    return (
        f"{mark} {result['metodo']:<28s} {result['status']!s:<4s} "
        f"{kind:<26s} {result['tamanho']:<8d} {result['marcador'] or '-'}"
    )


class Probe:
    def __init__(self, include_playwright: bool, out_file: str | None):
        self.results: list[ProbeResult] = []
        self.include_playwright = include_playwright
        self.out_file = out_file

    def add(self, metodo: str, url: str, status, body: str, headers: dict, tempo: float) -> None:
        tipo, marcador = classify(status, body, headers)
        result = {
            "metodo": metodo,
            "url": url,
            "status": status,
            "tipo": tipo,
            "tamanho": len(body or ""),
            "marcador": marcador,
            "tempo_s": round(tempo, 2),
            "corpo": _truncate(body),
        }
        self.results.append(result)
        print(_summary(result))

    def probe_httpx(self, url: str, headers: dict | None = None, method: str = "GET", **kwargs) -> None:
        import httpx

        name = f"httpx:{method}"
        t0 = time.time()
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True, headers=headers or BROWSER_HEADERS) as client:
                resp = client.request(method, url, **kwargs)
            self.add(name, url, resp.status_code, resp.text, dict(resp.headers), time.time() - t0)
        except Exception as e:
            self.add(name, url, None, "", {"err": str(e)}, time.time() - t0)

    def probe_requests(self, url: str, headers: dict | None = None) -> None:
        import requests

        t0 = time.time()
        try:
            resp = requests.get(url, headers=headers or BROWSER_HEADERS, timeout=30.0)
            self.add("requests", url, resp.status_code, resp.text, dict(resp.headers), time.time() - t0)
        except Exception as e:
            self.add("requests", url, None, "", {"err": str(e)}, time.time() - t0)

    def probe_curl(self, url: str, impersonate: str, headers: dict | None = None, warmup_url: str | None = None) -> None:
        name = f"curl:{impersonate}"
        if warmup_url:
            name = f"curl:{impersonate}+warmup"
        t0 = time.time()
        try:
            from curl_cffi import requests as curl_requests

            session = curl_requests.Session(timeout=30.0, impersonate=impersonate)
            if warmup_url:
                session.get(warmup_url, headers=headers or BROWSER_HEADERS)
            resp = session.get(url, headers=headers or BROWSER_HEADERS)
            self.add(name, url, resp.status_code, resp.text, dict(resp.headers), time.time() - t0)
        except Exception as e:
            self.add(name, url, None, "", {"err": str(e)}, time.time() - t0)

    def probe_graphql(self, url: str, impersonate: str | None, query: str, term: str) -> None:
        payload = {"query": query, "variables": {"term": term, "first": 10}}
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": UA_CHROME,
        }
        t0 = time.time()
        try:
            if impersonate:
                from curl_cffi import requests as curl_requests

                resp = curl_requests.post(url, json=payload, headers=headers, timeout=30.0, impersonate=impersonate)
            else:
                import httpx

                with httpx.Client(timeout=30.0, follow_redirects=True, headers=headers) as client:
                    resp = client.post(url, json=payload)
            name = f"graphql:{impersonate or 'httpx'}"
            self.add(name, url, resp.status_code, resp.text, dict(resp.headers), time.time() - t0)
        except Exception as e:
            name = f"graphql:{impersonate or 'httpx'}"
            self.add(name, url, None, "", {"err": str(e)}, time.time() - t0)

    def probe_playwright(self, url: str, timeout_ms: int = 45000) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.add("playwright", url, None, "", {"err": "playwright nao instalado"}, 0.0)
            return

        name = "playwright"
        t0 = time.time()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=UA_CHROME)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=min(timeout_ms, 30000))
                    page.wait_for_timeout(4000)
                    body = page.content()
                    title = page.title()
                    markers = [m for m in CF_CHALLENGE_STRONG + CF_PRESENT_WEAK if m.lower() in body.lower()]
                    self.add(
                        name,
                        url,
                        200 if not markers else 403,
                        body,
                        {"title": title, "markers": ",".join(markers)},
                        time.time() - t0,
                    )
                    if self.include_playwright and markers:
                        shot = Path("data/probe_screenshots") / f"pw_{int(time.time())}.png"
                        shot.parent.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(shot))
                        print(f"    screenshot: {shot}")
                finally:
                    browser.close()
        except Exception as e:
            self.add(name, url, None, "", {"err": str(e)}, time.time() - t0)

    def run_tiendeo(self) -> None:
        print("\n=== TIENDEO ===")
        for imp in IMPERSONATES:
            self.probe_curl(f"{TIENDEO_BASE}/santos", imp)
        self.probe_curl(f"{TIENDEO_BASE}/santos", "chrome124", warmup_url=f"{TIENDEO_BASE}/")
        self.probe_curl(f"{TIENDEO_BASE}/santos", "chrome124", headers={**BROWSER_HEADERS, "User-Agent": UA_MOBILE})
        self.probe_httpx(f"{TIENDEO_BASE}/santos")
        self.probe_requests(f"{TIENDEO_BASE}/santos")
        api_url = (
            f"{TIENDEO_BASE}/api/v2/offers?"
            f"city=santos&lat=-23.96&lng=-46.33&radius=50&limit=100"
        )
        self.probe_httpx(api_url)
        self.probe_curl(api_url, "chrome124")
        if self.include_playwright:
            self.probe_playwright(f"{TIENDEO_BASE}/santos")

    def run_carrefour(self) -> None:
        print("\n=== CARREFOUR ===")
        category = f"{CARREFOUR_BASE}/categoria/mercearia"
        busca = f"{CARREFOUR_BASE}/busca?q={quote('leite condensado')}"
        for url, label in ((category, "categoria"), (busca, "busca")):
            self.probe_httpx(url)
            self.probe_curl(url, "chrome124")
        self.probe_curl(category, "chrome124", headers={**BROWSER_HEADERS, "User-Agent": UA_MOBILE})
        gql = f"{CARREFOUR_BASE}/_v/segment/graphql/v1"
        self.probe_graphql(gql, None, CARREFOUR_GRAPHQL_QUERY, "leite condensado")
        self.probe_graphql(gql, "chrome124", CARREFOUR_GRAPHQL_QUERY, "leite condensado")
        vtex = f"{CARREFOUR_BASE}/api/catalog_system/pub/products/search/{quote('leite condensado')}"
        self.probe_httpx(vtex)
        self.probe_curl(vtex, "chrome124")
        if self.include_playwright:
            self.probe_playwright(category)

    def run_carrefour_intelligent_search(self) -> None:
        print("\n=== CARREFOUR INTELLIGENT SEARCH ===")
        term = quote("leite condensado")
        for url in (
            f"{CARREFOUR_BASE}/_v/api/intelligent-search/product_search/{term}?from=0&to=49",
            f"{CARREFOUR_BASE}/api/intelligent-search/product_search/{term}?from=0&to=49",
        ):
            self.probe_httpx(url)
            self.probe_curl(url, "chrome124")

    def run_wayback_tiendeo(self) -> None:
        print("\n=== TIENDEO VIA WAYBACK MACHINE ===")
        t0 = time.time()
        try:
            import httpx

            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                avail = client.get(
                    "https://archive.org/wayback/available",
                    params={"url": "tiendeo.com.br/santos"},
                )
                if avail.status_code != 200:
                    self.add("wayback", "archive.org/wayback/available", avail.status_code, avail.text, {}, time.time() - t0)
                    return
                data = avail.json()
            snap = (data.get("archived_snapshots") or {}).get("closest") or {}
            snap_url = snap.get("url")
            if not snap_url:
                self.add("wayback", "tiendeo.com.br/santos", avail.status_code, "", {"err": "sem snapshot"}, time.time() - t0)
                return
            self.add("wayback_discovery", "archive.org/wayback/available", 200, json.dumps(data), {}, time.time() - t0)
            self.probe_httpx(snap_url)
            self.probe_curl(snap_url, "chrome124")
        except Exception as e:
            self.add("wayback", "archive.org", None, "", {"err": str(e)}, time.time() - t0)

    def run_extra(self, url: str) -> None:
        print(f"\n=== EXTRA: {url} ===")
        self.probe_httpx(url)
        self.probe_curl(url, "chrome124")

    def report(self) -> int:
        print("\n" + "=" * 90)
        print("RESUMO - Sonda Anti-Bot")
        print("=" * 90)
        for r in self.results:
            print(_summary(r))

        wins = [r for r in self.results if r["tipo"] in ("200_real", "200_real_cf_presente", "cloudflare_challenge_200")]
        all_blocked = [r for r in self.results if r["tipo"] in ("cloudflare_403", "403_generico", "cloudflare_429")]
        print("-" * 90)
        if wins:
            print(f"VENCEDORES ({len(wins)}):")
            for w in wins:
                print(f"  OK {w['metodo']:<28s} {w['url'][:70]}")
        else:
            print("NENHUM metodo retornou 200 real.")
        if all_blocked and not wins:
            print(f"TODOS os {len(all_blocked)} metodos foram bloqueados no runner.")
            print("Isso sugere bloqueio por reputacao de IP (datacenter) — verificar corpo em probe_results.json")
        return 0

    def save(self) -> None:
        if self.out_file:
            Path(self.out_file).parent.mkdir(parents=True, exist_ok=True)
            Path(self.out_file).write_text(json.dumps(self.results, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\nJSON salvo em {self.out_file}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sonda anti-bot Tiendeo/Carrefour")
    parser.add_argument("--json", type=str, default=None, help="Caminho do JSON de saída")
    parser.add_argument("--playwright", action="store_true", help="Incluir testes Playwright (lentos)")
    parser.add_argument("urls", nargs="*", help="URLs extras para testar")
    args = parser.parse_args()

    probe = Probe(include_playwright=args.playwright, out_file=args.json)
    probe.run_tiendeo()
    probe.run_carrefour()
    probe.run_carrefour_intelligent_search()
    probe.run_wayback_tiendeo()
    for url in args.urls:
        probe.run_extra(url)
    probe.save()
    return probe.report()


if __name__ == "__main__":
    raise SystemExit(main())
