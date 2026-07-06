"""Test Spani store slugs for PDF links."""

import re

import httpx

stores = {
    "Barra Funda": "sao-paulo-barra-funda",
    "Vila Prudente": "vila-prudente",
    "Vila Formosa": "vila-formosa",
    "Parelheiros": "sao-paulo-parelheiros",
    "Tatuate": "tatuate",
    "Caraguatatuba": "caraguatatuba",
    "Mogi das Cruzes": "mogi-das-cruzes",
    "Sao Jose dos Campos": "sao-jose-dos-campos",
    "Maua": "maua",
}

with httpx.Client(timeout=15, follow_redirects=True, verify=False) as client:
    for name, slug in stores.items():
        url = f"https://lojas.spani.com.br/lojas/{slug}"
        try:
            r = client.get(url)
            if r.status_code == 200:
                pdfs = re.findall(r'spani-tabloides[^\'"]*\.pdf', r.text)
                if pdfs:
                    print(f"{name:25s} {slug:30s} -> {pdfs[0]}")
                else:
                    print(f"{name:25s} {slug:30s} -> 200 mas sem PDF")
            else:
                print(f"{name:25s} {slug:30s} -> {r.status_code}")
        except Exception as e:
            print(f"{name:25s} {slug:30s} -> ERRO {e}")
