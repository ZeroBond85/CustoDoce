"""Check other stores sitemaps."""

import re

import httpx

urls = [
    "https://www.tendaatacado.com.br/sitemap.xml",
    "https://www.maxatacadista.com.br/sitemap.xml",
    "https://roldao.com.br/sitemap.xml",
    "https://www.samsclub.com.br/sitemap.xml",
    "https://www.makro.com.br/sitemap.xml",
]

with httpx.Client(timeout=30, follow_redirects=True, verify=False) as client:
    for url in urls:
        try:
            r = client.get(url)
            if r.status_code == 200:
                matches = re.findall(r"<loc>([^<]+)</loc>", r.text)
                encartes = [
                    u
                    for u in matches
                    if any(w in u.lower() for w in ["encarte", "oferta", "folheto", "tabloide", "pdf"])
                ]
                store_name = url.split("//")[1].split("/")[0]
                print(f"{store_name}: {len(encartes)} encartes")
                for u in encartes[:5]:
                    print(f"  {u}")
            else:
                print(f"{url}: {r.status_code}")
        except Exception as e:
            print(f"{url}: ERRO - {e}")
