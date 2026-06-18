"""Search Tenda for flyer keywords."""
import httpx
import re

urls = [
    "https://www.tendaatacado.com.br/institucional/nossas-ofertas",
    "https://www.tendaatacado.com.br/ofertas",
    "https://www.tendaatacado.com.br/encarte",
    "https://www.tendaatacado.com.br/folheto",
    "https://www.tendaatacado.com.br/jornal-de-ofertas",
]

with httpx.Client(timeout=20, follow_redirects=True, verify=False) as client:
    for url in urls:
        try:
            r = client.get(url)
            ct = r.headers.get("content-type", "")
            print(f"{r.status_code} {url} -> {ct[:40]} ({len(r.content)} bytes)")
            if r.status_code == 200:
                pdfs = re.findall(r'href=[\'"]([^\'"]*\.pdf)', r.text, re.IGNORECASE)
                if pdfs:
                    for p in pdfs:
                        print(f"  PDF: {p}")
                # Look for PDF viewer embed
                iframes = re.findall(r'<iframe[^>]+src=[\'"]([^\'"]*)', r.text, re.IGNORECASE)
                if iframes:
                    for i in iframes:
                        print(f"  IFRAME: {i}")
        except Exception as e:
            print(f"ERRO {url} -> {e}")
