"""Test Assai offer pages for PDF links."""

import httpx
import re

cities = [
    ("Santos", "sao-paulo/assai-santos"),
    ("São Vicente", "sao-paulo/assai-sao-vicente"),
    ("Praia Grande", "sao-paulo/assai-praia-grande"),
]

with httpx.Client(timeout=20, follow_redirects=True, verify=False) as client:
    for city_name, city_slug in cities:
        url = f"https://www.assai.com.br/ofertas/{city_slug}"
        try:
            r = client.get(url)
            if r.status_code == 200:
                # Look for PDF links, download buttons, etc.
                pdfs = re.findall(r'href=[\'"]([^\'"]+\.pdf)', r.text, re.IGNORECASE)
                # Also look for print/offline links
                prints = re.findall(
                    r'(?:print|imprimir|offline|download|baixar)[^>]*href=[\'"]([^\'"]+)', r.text, re.IGNORECASE
                )
                # Check for printpdf pattern
                printpdfs = re.findall(r'printpdf[^>]*href=[\'"]([^\'"]+)', r.text, re.IGNORECASE)

                print(f"=== Assai {city_name} ===")
                if pdfs:
                    for p in pdfs:
                        print(f"  PDF: {p}")
                if printpdfs:
                    for p in printpdfs:
                        print(f"  PrintPDF: {p}")
                if prints:
                    for p in prints:
                        print(f"  Print/Download: {p}")
                if not pdfs and not printpdfs and not prints:
                    print("  Sem links óbvios de PDF/print")
        except Exception as e:
            print(f"Assai {city_name}: ERRO - {e}")
