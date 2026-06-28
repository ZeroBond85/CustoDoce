"""Test other stores PDF patterns."""

import httpx

stores = {
    "Atacadao": "https://atacadao.encarte.br.com/images/atacadao/atacadao-weekly-ad.pdf",
    "Roldao": "https://roldao.encarte.br.com/images/roldao/roldao-weekly-ad.pdf",
    "Tenda": "https://tendaatacado.encarte.br.com/images/tendaatacado/tendaatacado-weekly-ad.pdf",
    "Max": "https://maxatacadista.encarte.br.com/images/maxatacadista/maxatacadista-weekly-ad.pdf",
    "Spani": "https://spani.encarte.br.com/images/spani/spani-weekly-ad.pdf",
    "Mercadao": "https://mercadaoatacadista.encarte.br.com/images/mercadaoatacadista/mercadaoatacadista-weekly-ad.pdf",
}

with httpx.Client(timeout=30, follow_redirects=True, verify=False) as client:
    for name, url in stores.items():
        try:
            r = client.head(url)
            ct = r.headers.get("content-type", "")
            print(f"{name:12s} {r.status_code} -> {ct}")
        except Exception as e:
            print(f"{name:12s} ERRO -> {type(e).__name__}")

    # Test Spani S3 pattern
    print("\n--- Spani S3 pattern ---")
    spani_pdfs = [
        "https://spani-tabloides-bucket.s3.us-east-1.amazonaws.com/tabloides/sao-paulo-barra-funda-5jbmvbotagkbgjmwfrlwk6.pdf",
        "https://spani-tabloides-bucket.s3.us-east-1.amazonaws.com/tabloides/sao-paulo-barra-funda.pdf",
        "https://spani-tabloides-bucket.s3.us-east-1.amazonaws.com/tabloides/sao-paulo-vila-carrao.pdf",
    ]
    for url in spani_pdfs:
        try:
            r = client.head(url)
            ct = r.headers.get("content-type", "")
            cl = r.headers.get("content-length", "?")
            print(f"{r.status_code} -> {ct[:40]} ({cl} bytes)")
        except Exception as e:
            print(f"ERRO {url} -> {e}")
