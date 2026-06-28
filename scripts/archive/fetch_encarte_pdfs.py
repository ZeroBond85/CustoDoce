"""Fetch encarte.br.com pages for PDF links."""

import httpx
import re

urls = [
    ("Assai", "https://assai.encarte.br.com/"),
    ("Atacadao", "https://atacadao.encarte.br.com/"),
    ("Roldao", "https://roldao.encarte.br.com/"),
    ("Tenda", "https://tendaatacado.encarte.br.com/"),
    ("Max", "https://maxatacadista.encarte.br.com/"),
]

with httpx.Client(timeout=20, follow_redirects=True, verify=False) as client:
    for name, url in urls:
        try:
            r = client.get(url)
            if r.status_code == 200:
                pdfs = re.findall(r'href=[\'"]([^\'"]+\.pdf)', r.text, re.IGNORECASE)
                downloads = re.findall(r'(?:download|baixar|pdf)[^>]*href=[\'"]([^\'"]+)', r.text, re.IGNORECASE)
                if pdfs:
                    print(f"{name}: PDFs encontrados:")
                    for p in pdfs[:5]:
                        print(f"  {p}")
                elif downloads:
                    print(f"{name}: Download links:")
                    for d in downloads[:5]:
                        print(f"  {d}")
                else:
                    print(f"{name}: HTML 200 mas sem links PDF ({len(r.text)} chars)")
            else:
                print(f"{name}: {r.status_code}")
        except Exception as e:
            print(f"{name}: ERRO - {type(e).__name__}: {e}")
