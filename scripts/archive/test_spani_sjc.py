"""Check Spani SJC store page."""
import httpx
import re

# Try different SJC slugs
sjc_slugs = [
    "sao-jose-dos-campos",
    "sao-jose-dos-campos-aquarius",
    "sao-jose-dos-campos-vista-verde",
    "sjc",
    "sjc-aquarius",
    "sjc-vista-verde",
    "aquarius",
    "vista-verde",
]

with httpx.Client(timeout=15, follow_redirects=True, verify=False) as client:
    for slug in sjc_slugs:
        url = f"https://lojas.spani.com.br/lojas/{slug}"
        try:
            r = client.get(url)
            if r.status_code == 200:
                pdfs = re.findall(r'spani-tabloides[^\'"]*\.pdf', r.text)
                if pdfs:
                    print(f"OK  {slug:30s} -> {pdfs[0]}")
                else:
                    print(f"200 {slug:30s} -> sem PDF")
            else:
                print(f"{r.status_code} {slug}")
        except Exception as e:
            print(f"ERRO {slug} -> {e}")
