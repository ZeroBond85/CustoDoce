"""Search Roldão for flyer keywords."""

import httpx
import re

urls = [
    "https://roldao.com.br/ofertas-do-roldao/",
    "https://roldao.com.br/encarte",
    "https://roldao.com.br/folheto",
    "https://roldao.com.br/jornal-de-ofertas",
    "https://roldao.com.br/ofertas",
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
        except Exception as e:
            print(f"ERRO {url} -> {e}")
