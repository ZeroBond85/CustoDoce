"""Extract links from Atacadão ofertas page."""
import httpx
import re

url = "https://www.atacadao.com.br/ofertas"
with httpx.Client(timeout=20, follow_redirects=True, verify=False) as client:
    r = client.get(url)
    print(f"Status: {r.status_code}, Len: {len(r.text)}")
    links = re.findall(r'href=[\'"]([^\'"]*)[\'"]', r.text)
    pdfs = [l for l in links if ".pdf" in l.lower()]
    ofertas = [l for l in links if any(w in l.lower() for w in ["folheto", "encarte", "oferta", "print", "download", "pdf"])]
    print("PDF links:")
    for p in pdfs[:10]:
        print(f"  {p}")
    print("Oferta/Print links:")
    for o in ofertas[:15]:
        print(f"  {o}")
