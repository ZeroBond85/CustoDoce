"""Discover all store locations for each chain."""

import re

import httpx

with httpx.Client(timeout=20, follow_redirects=True, verify=False) as client:
    # 1. Max - find all loja IDs
    print("=== MAX ATACADISTA ===")
    r = client.get("https://www.maxatacadista.com.br/lojas/")
    if r.status_code == 200:
        # Look for loja links
        lojas = re.findall(r"/lojas/encartes-e-videos/\?loja=(\d+)", r.text)
        lojas = list(set(lojas))
        print(f"Loja IDs: {lojas[:20]}")
        # Also look for store names
        store_links = re.findall(r'href=[\'"]([^\'"]*lojas/[^\'"]*)', r.text)
        print(f"Store links: {store_links[:10]}")

    # 2. Spani - find all store pages
    print("\n=== SPANI ===")
    r = client.get("https://lojas.spani.com.br/")
    if r.status_code == 200:
        stores = re.findall(r"lojas\.spani\.com\.br/lojas/([a-z0-9\-]+)", r.text)
        stores = list(set(stores))
        print(f"Stores: {stores[:30]}")

    # 3. Tenda - find all stores
    print("\n=== TENDA ===")
    r = client.get("https://www.tendaatacado.com.br/institucional/nossas-lojas/")
    if r.status_code == 200:
        stores = re.findall(r"nossas-lojas/([a-z0-9\-]+)", r.text)
        stores = list(set(stores))
        print(f"Stores: {stores[:30]}")

    # 4. 4. Roldão
    print("\n=== ROLDÃO ===")
    r = client.get("https://roldao.com.br/lojas/")
    if r.status_code == 200:
        stores = re.findall(r"lojas/([a-z0-9\-]+)", r.text)
        stores = list(set(stores))
        print(f"Stores: {stores[:30]}")
