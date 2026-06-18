"""Discover real Tier 1 PDF URLs for each store."""
import httpx
import re

today = "2026-06-18"
week = "25"

# Common encarte URL patterns to try per store
patterns = {
    "Assai": [
        f"https://www.assai.com.br/encarte/semana-{week}.pdf",
        "https://www.assai.com.br/encarte",
        "https://www.assai.com.br/ofertas",
    ],
    "Atacadao": [
        f"https://www.atacadao.com.br/encarte/semana-{week}.pdf",
        "https://www.atacadao.com.br/ofertas",
    ],
    "Tenda": [
        f"https://www.tendaatacado.com.br/encarte/semana-{week}.pdf",
        "https://www.tendaatacado.com.br/ofertas",
    ],
    "Roldao": [
        f"https://www.roldao.com.br/encarte/semana-{week}.pdf",
        "https://roldao.com.br/encarte",
    ],
    "Sams Club": [
        f"https://www.samsclub.com.br/encarte/semana-{week}.pdf",
        "https://www.samsclub.com.br/ofertas",
    ],
    "Makro": [
        "https://www.makro.com.br/ofertas",
    ],
    "Max": [
        f"https://www.maxatacadista.com.br/encarte/semana-{week}.pdf",
        "https://www.maxatacadista.com.br/ofertas",
    ],
}

with httpx.Client(timeout=15, follow_redirects=True, verify=False) as client:
    for store, urls in patterns.items():
        print(f"\n=== {store} ===")
        for url in urls:
            try:
                r = client.get(url)
                if r.status_code == 200:
                    # Check if it's HTML looking for PDF links
                    if "text/html" in r.headers.get("content-type", ""):
                        # Search for PDF links in the HTML
                        pdfs = re.findall(r'href=[\'"]?([^\'" >]+\.pdf)', r.text)
                        if pdfs:
                            print("  HTML 200 - PDFs encontrados:")
                            for p in pdfs[:5]:
                                print(f"    {p}")
                        else:
                            print("  HTML 200 - sem links PDF na pagina")
                    else:
                        print(f"  {r.status_code} {url} ({r.headers.get('content-type', '?')[:30]})")
                else:
                    print(f"  {r.status_code} {url}")
            except Exception as e:
                print(f"  ERRO: {type(e).__name__} - {url}")
