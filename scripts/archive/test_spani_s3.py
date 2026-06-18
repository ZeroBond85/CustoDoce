"""Test Spani S3 bucket with city slugs."""
import httpx

cities = [
    "santos", "sao-vicente", "praia-grande", "mongagua", "itanhaem", "peruibe",
    "barra-funda", "jabaquara", "interlagos", "sao-bernardo-do-campo",
    "diadema", "santo-andre", "osasco", "guarulhos", "campinas",
    "sao-caetano-do-sul", "sao-jose-dos-campos", "sorocaba",
    "braganca-paulista", "ribeirao-preto", "bauru", "jaboticabal",
    "franca", "marilia", "jau", "aracatuba", "presidente-prudente",
]

with httpx.Client(timeout=15, follow_redirects=True, verify=False) as client:
    for city in cities:
        url = f"https://spani-tabloides-bucket.s3.us-east-1.amazonaws.com/tabloides/{city}.pdf"
        try:
            r = client.head(url)
            if r.status_code == 200:
                print(f"OK  {city} -> {r.headers.get('content-length', '?')} bytes")
        except httpx.HTTPError:
            pass
