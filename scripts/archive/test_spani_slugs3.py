"""Test Spani slugs from website."""

import re

import httpx

stores = {
    "Parelheiros": [
        "sao-paulo-parelheiros",
        "parelheiros",
        "sp-parelheiros",
    ],
    "SJC Aquarius": [
        "sao-jose-dos-campos-aquarius",
        "sjc-aquarius",
        "aquarius",
        "sao-jose-dos-campos",
    ],
    "SJC Vista Verde": [
        "sao-jose-dos-campos-vista-verde",
        "sjc-vista-verde",
        "vista-verde",
    ],
}

with httpx.Client(timeout=15, follow_redirects=True, verify=False) as client:
    for name, slugs in stores.items():
        for slug in slugs:
            url = f"https://lojas.spani.com.br/lojas/{slug}"
            try:
                r = client.get(url)
                if r.status_code == 200:
                    pdfs = re.findall(r'spani-tabloides[^\'"]*\.pdf', r.text)
                    if pdfs:
                        print(f"OK  {name:25s} {slug:30s} -> {pdfs[0]}")
                        break
                    else:
                        print(f"200 {name:25s} {slug:30s} -> sem PDF")
            except httpx.HTTPError:
                pass
        else:
            print(f"404 {name:25s} NENHUM slug funcional")
