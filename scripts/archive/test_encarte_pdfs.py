"""Test encarte.br.com PDF patterns for all stores."""
import httpx

urls = [
    ("Assai", "https://assai.encarte.br.com/images/assai/assai-weekly-ad.pdf"),
    ("Atacadao", "https://atacadao.encarte.br.com/images/atacadao/atacadao-weekly-ad.pdf"),
    ("Roldao", "https://roldao.encarte.br.com/images/roldao/roldao-weekly-ad.pdf"),
    ("Tenda", "https://tendaatacado.encarte.br.com/images/tendaatacado/tendaatacado-weekly-ad.pdf"),
    ("Max", "https://maxatacadista.encarte.br.com/images/maxatacadista/maxatacadista-weekly-ad.pdf"),
    ("Spani", "https://spani.encarte.br.com/images/spani/spani-weekly-ad.pdf"),
    ("Mercadao", "https://mercadaoatacadista.encarte.br.com/images/mercadaoatacadista/mercadaoatacadista-weekly-ad.pdf"),
]

with httpx.Client(timeout=30, follow_redirects=True, verify=False) as client:
    for name, url in urls:
        try:
            r = client.head(url)
            ct = r.headers.get("content-type", "")
            cl = r.headers.get("content-length", "?")
            print(f"{name:12s} {r.status_code} -> {ct} ({cl} bytes)")
        except Exception as e:
            print(f"{name:12s} ERRO -> {type(e).__name__}")
