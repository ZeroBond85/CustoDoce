"""Test Tier 1 PDF URLs."""

from datetime import date
import httpx

today = date.today()
week = today.isocalendar().week
print(f"Hoje: {today}, Semana ISO: {week}\n")

urls = [
    ("Assai", f"https://www.assai.com.br/encarte/semana-{week}.pdf"),
    ("Atacadao", f"https://www.atacadao.com.br/encarte/semana-{week}.pdf"),
    ("Spani", f"https://www.spani.com.br/encarte/semana-{week}.pdf"),
    ("Mercadao", f"https://www.mercadaoatacadista.com.br/encarte/semana-{week}.pdf"),
    ("Tenda", f"https://www.tendaatacado.com.br/encarte/semana-{week}.pdf"),
    ("Roldao", f"https://www.roldao.com.br/encarte/semana-{week}.pdf"),
    ("Sams Club", f"https://www.samsclub.com.br/encarte/semana-{week}.pdf"),
    ("Makro", f"https://www.makro.com.br/encarte/semana-{week}.pdf"),
    ("Max Atacadista", f"https://www.maxatacadista.com.br/encarte/semana-{week}.pdf"),
]

with httpx.Client(timeout=15, follow_redirects=True) as client:
    for name, url in urls:
        try:
            r = client.head(url)
            print(f"{name:15s} {r.status_code} {url}")
        except Exception as e:
            print(f"{name:15s} ERRO  {url}")
            print(f"           {type(e).__name__}: {e}")
