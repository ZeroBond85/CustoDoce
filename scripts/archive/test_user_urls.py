"""Test user-provided URLs."""
import httpx
import re

urls = [
    ("Max", "https://www.maxatacadista.com.br/lojas/encartes-e-videos/?loja=129"),
    ("Spani", "https://lojas.spani.com.br/lojas/sao-paulo-barra-funda"),
    ("Mercadao", "https://mercadaoatacadista.com.br/ofertas"),
    ("Tenda", "https://www.tendaatacado.com.br/institucional/nossas-ofertas"),
]

with httpx.Client(timeout=20, follow_redirects=True, verify=False) as client:
    for name, url in urls:
        try:
            r = client.get(url)
            ct = r.headers.get("content-type", "")
            print(f"{name}: {r.status_code} {url} -> {ct[:40]} ({len(r.content)} bytes)")
            if r.status_code == 200:
                pdfs = re.findall(r'href=[\'"]([^\'"]*\.pdf)', r.text, re.IGNORECASE)
                if pdfs:
                    for p in pdfs:
                        print(f"  PDF: {p}")
                # Look for iframe embeds
                iframes = re.findall(r'<iframe[^>]+src=[\'"]([^\'"]*)', r.text, re.IGNORECASE)
                if iframes:
                    for i in iframes:
                        print(f"  IFRAME: {i}")
        except Exception as e:
            print(f"ERRO {name} {url} -> {e}")
