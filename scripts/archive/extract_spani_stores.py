"""Extract Spani store slugs."""
import httpx
import re

url = "https://lojas.spani.com.br/"
with httpx.Client(timeout=20, follow_redirects=True, verify=False) as client:
    r = client.get(url)
    links = re.findall(r'href=[\'"](/lojas/[^\'"]*)', r.text)
    stores = set()
    for l in links:
        match = re.search(r"/lojas/([a-z0-9\-]+)", l)
        if match:
            stores.add(match.group(1))
    print(f"Found {len(stores)} store slugs:")
    for s in sorted(stores):
        print(f"  {s}")
