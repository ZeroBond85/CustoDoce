"""Test Assai offer page pattern."""
import httpx

# Test Assai city-specific offer pages
cities = [
    ("Santos", "sao-paulo/assai-santos"),
    ("São Vicente", "sao-paulo/assai-sao-vicente"),
    ("Praia Grande", "sao-paulo/assai-praia-grande"),
    ("Itanhaém", "sao-paulo/assai-itanhaem"),
    ("Mongaguá", "sao-paulo/assai-mongagua"),
]

with httpx.Client(timeout=20, follow_redirects=True, verify=False) as client:
    for city_name, city_slug in cities:
        url = f"https://www.assai.com.br/ofertas/{city_slug}"
        try:
            r = client.get(url)
            print(f"Assai {city_name}: {r.status_code} -> {url}")
            if r.status_code == 200:
                # Check for PDF link in HTML
                import re
                pdfs = re.findall(r'href=[\'"]([^\'"]+\.pdf)', r.text, re.IGNORECASE)
                if pdfs:
                    for p in pdfs[:3]:
                        print(f"  PDF: {p}")
        except Exception as e:
            print(f"Assai {city_name}: ERRO - {e}")
