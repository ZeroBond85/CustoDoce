"""Explore Atacadao and other sites for PDF/flyer patterns."""
import httpx
import re

urls = [
    'https://www.atacadao.com.br/institucional/nossas-lojas',
    'https://www.atacadao.com.br/ofertas',
    'https://www.atacadao.com.br/ofertas/sao-paulo',
    'https://www.atacadao.com.br/encarte',
]

with httpx.Client(timeout=20, follow_redirects=True, verify=False) as client:
    for url in urls:
        try:
            r = client.get(url)
            ct = r.headers.get('content-type', '')
            print(f"{r.status_code} {url} -> {ct[:50]} ({len(r.content)} bytes)")
            if r.status_code == 200 and 'html' in ct:
                pdfs = re.findall(r'href=[\'"]([^\'"]*\.pdf)', r.text, re.IGNORECASE)
                folhetos = re.findall(r'href=[\'"]([^\'"]*(?:folheto|encarte|ofertas)[^\'"]*)', r.text, re.IGNORECASE)
                if pdfs:
                    print(f"  PDFs: {pdfs[:5]}")
                if folhetos:
                    print(f"  Folhetos: {folhetos[:5]}")
        except Exception as e:
            print(f"ERRO {url} -> {e}")
