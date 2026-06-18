"""Test Spani slugs that failed."""
import httpx
import re

stores = {
    "Parelheiros": [
        "parelheiros",
        "sao-paulo-parelheiros",
        "sao-paulo---parelheiros",
    ],
    "Tatuate": [
        "tatuate",
        "tatuape",
        "sao-paulo-tatuape",
    ],
    "Sao Jose dos Campos": [
        "sao-jose-dos-campos",
        "sao-jose-dos-campos-aquarius",
        "sao-jose-dos-campos-vista-verde",
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
                        print(f"{name:25s} {slug:30s} -> {pdfs[0]}")
                        break
            except:
                pass
        else:
            print(f"{name:25s} NENHUM slug funcional")
