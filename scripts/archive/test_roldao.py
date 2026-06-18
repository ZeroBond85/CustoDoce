"""Test Roldão ofertas page."""
import httpx
import re

url = "https://roldao.com.br/ofertas-do-roldao/"
with httpx.Client(timeout=20, follow_redirects=True, verify=False) as client:
    r = client.get(url)
    ct = r.headers.get("content-type", "")
    print(f"{r.status_code} {url} -> {ct[:50]} ({len(r.content)} bytes)")
    if r.status_code == 200:
        pdfs = re.findall(r'href=[\'"]([^\'"]*\.pdf)', r.text, re.IGNORECASE)
        print(f"PDFs: {pdfs[:5]}")
        prints = re.findall(r"printpdf", r.text, re.IGNORECASE)
        print(f"PrintPDF mentions: {len(prints)}")
