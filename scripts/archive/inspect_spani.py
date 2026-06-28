"""Inspect Spani page for data."""

import httpx
import re

url = "https://lojas.spani.com.br/"
with httpx.Client(timeout=20, follow_redirects=True, verify=False) as client:
    r = client.get(url)
    # Save full page for manual inspection
    with open("spani_full.html", "w") as f:
        f.write(r.text)
    print(f"Full page saved, length: {len(r.text)}")
    # Search for any store slug patterns
    matches = re.findall(r"lojas/([a-z0-9\-]+)", r.text)
    if matches:
        stores = set(matches)
        print(f"Found {len(stores)} store slugs:")
        for s in sorted(stores)[:50]:
            print(f"  {s}")
    else:
        print("No store slugs found in HTML")
