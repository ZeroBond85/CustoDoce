"""Discover all store locations for each chain - detailed."""
import httpx
import re

with httpx.Client(timeout=20, follow_redirects=True, verify=False) as client:
    # 1. Max - try different pages
    print("=== MAX ATACADISTA ===")
    urls = [
        "https://www.maxatacadista.com.br/lojas/",
        "https://www.maxatacadista.com.br/lojas/encartes-e-videos/",
        "https://www.maxatacadista.com.br/institucional/nossas-lojas/",
    ]
    for url in urls:
        r = client.get(url)
        print(f"\n{url} -> {r.status_code}")
        if r.status_code == 200:
            # Look for store selectors
            lojas = re.findall(r'loja=(\d+)', r.text)
            lojas = list(set(lojas))
            if lojas:
                print(f"  Loja IDs: {lojas[:30]}")
            # Look for select options
            options = re.findall(r'<option[^>]+value="(\d+)"', r.text)
            if options:
                print(f"  Option values: {options[:30]}")

    # 2. Spani - find all stores
    print("\n=== SPANI ===")
    r = client.get("https://lojas.spani.com.br/")
    if r.status_code == 200:
        # Look for store links
        stores = re.findall(r'/lojas/([a-z0-9\-]+)', r.text)
        stores = list(set(stores))
        print(f"Stores: {stores[:50]}")

    # 3. Tenda - try their store finder
    print("\n=== TENDA ===")
    r = client.get("https://www.tendaatacado.com.br/nossas-lojas/")
    if r.status_code == 200:
        stores = re.findall(r'nossas-lojas/([a-z0-9\-]+)', r.text)
        stores = list(set(stores))
        print(f"Stores: {stores[:50]}")
