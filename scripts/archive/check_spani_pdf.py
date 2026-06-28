"""Check Spani lojas page for PDF pattern."""

import httpx
import re

url = "https://lojas.spani.com.br/lojas/sao-paulo-barra-funda"
with httpx.Client(timeout=20, follow_redirects=True, verify=False) as client:
    r = client.get(url)
    pdfs = re.findall(r'href=[\'"]([^\'"]*\.pdf)', r.text, re.IGNORECASE)
    print("Spani PDFs:")
    for p in pdfs:
        print(f"  {p}")
