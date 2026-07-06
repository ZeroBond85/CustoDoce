"""Check Atacadão download page content."""

import re

import httpx

url = "https://atacadao.encarte.br.com/download"
with httpx.Client(timeout=30, follow_redirects=True, verify=False) as client:
    r = client.get(url)
    print(f"Status: {r.status_code}, Len: {len(r.text)}")
    pdfs = re.findall(r'href=[\'"]([^\'"]*\.pdf)', r.text, re.IGNORECASE)
    print(f"PDFs: {pdfs}")
    iframes = re.findall(r'<iframe[^>]+src=[\'"]([^\'"]*)', r.text, re.IGNORECASE)
    print(f"IFrames: {iframes[:5]}")
