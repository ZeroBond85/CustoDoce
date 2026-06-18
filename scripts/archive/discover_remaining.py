"""Discover PDF patterns for remaining stores."""
import httpx
import re

with httpx.Client(timeout=30, follow_redirects=True, verify=False) as client:

    # 1. Tenda - check the nossas-ofertas page for PDF links
    print("=== TENDA ===")
    r = client.get("https://www.tendaatacado.com.br/institucional/nossas-ofertas")
    print(f"Status: {r.status_code}, Len: {len(r.text)}")
    # Look for PDF or iframe
    pdfs = re.findall(r'href=[\'"]([^\'"]*\.pdf)', r.text, re.IGNORECASE)
    iframes = re.findall(r'<iframe[^>]+src=[\'"]([^\'"]*)', r.text, re.IGNORECASE)
    print(f"PDFs: {pdfs[:5]}")
    print(f"Iframes: {iframes[:5]}")

    # 2. Roldão - check ofertas page
    print("\n=== ROLDAO ===")
    r = client.get("https://roldao.com.br/ofertas-do-roldao/")
    print(f"Status: {r.status_code}, Len: {len(r.text)}")
    pdfs = re.findall(r'href=[\'"]([^\'"]*\.pdf)', r.text, re.IGNORECASE)
    # Also look for links with 'oferta' or 'encarte' or 'folheto'
    oferta_links = re.findall(r'href=[\'"]([^\'"]*(?:oferta|encarte|folheto|tabloide)[^\'"]*)', r.text, re.IGNORECASE)
    print(f"PDFs: {pdfs[:5]}")
    print(f"Oferta links: {oferta_links[:5]}")

    # 3. Max - check the encartes page
    print("\n=== MAX ===")
    r = client.get("https://www.maxatacadista.com.br/lojas/encartes-e-videos/?loja=129")
    print(f"Status: {r.status_code}, Len: {len(r.text)}")
    pdfs = re.findall(r'href=[\'"]([^\'"]*\.pdf)', r.text, re.IGNORECASE)
    iframes = re.findall(r'<iframe[^>]+src=[\'"]([^\'"]*)', r.text, re.IGNORECASE)
    print(f"PDFs: {pdfs[:5]}")
    print(f"Iframes: {iframes[:5]}")

    # 4. Sam's Club
    print("\n=== SAM'S CLUB ===")
    r = client.get("https://www.samsclub.com.br/ofertas")
    print(f"Status: {r.status_code}, Len: {len(r.text)}")
    pdfs = re.findall(r'href=[\'"]([^\'"]*\.pdf)', r.text, re.IGNORECASE)
    print(f"PDFs: {pdfs[:5]}")

    # 5. Makro
    print("\n=== MAKRO ===")
    try:
        r = client.get("https://www.makro.com.br/ofertas")
        print(f"Status: {r.status_code}, Len: {len(r.text)}")
        pdfs = re.findall(r'href=[\'"]([^\'"]*\.pdf)', r.text, re.IGNORECASE)
        print(f"PDFs: {pdfs[:5]}")
    except Exception as e:
        print(f"ERRO: {e}")
