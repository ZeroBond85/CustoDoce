"""Scrape Spani store pages for PDF links."""

import httpx
import re

# Test a few Spani store pages
stores = [
    "sao-paulo-barra-funda",
    "santos",
    "sao-vicente",
    "praia-grande",
]

with httpx.Client(timeout=20, follow_redirects=True, verify=False) as client:
    for store in stores:
        url = f"https://lojas.spani.com.br/lojas/{store}"
        try:
            r = client.get(url)
            ct = r.headers.get("content-type", "")
            print(f"{store}: {r.status_code} -> {ct[:40]} ({len(r.content)} bytes)")
            if r.status_code == 200:
                pdfs = re.findall(r'href=[\'"]([^\'"]*\.pdf)', r.text, re.IGNORECASE)
                if pdfs:
                    for p in pdfs:
                        print(f"  PDF: {p}")
                # Also check for spani-tabloides in content
                s3_links = re.findall(r'spani-tabloides[^\'"]*\.pdf', r.text)
                if s3_links:
                    for s in s3_links:
                        print(f"  S3: {s}")
        except Exception as e:
            print(f"ERRO {store} -> {e}")
