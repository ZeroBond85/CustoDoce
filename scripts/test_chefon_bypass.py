"""Test Chefon bypass methods: curl_cffi, GraphQL, etc."""
import sys

sys.path.insert(0, ".")

BASE = "https://chefon.com.br"

def test_httpx_json_api():
    import httpx
    resp = httpx.get(f"{BASE}/collections/all/products.json", params={"limit": 3, "page": 1}, timeout=30)
    return resp.status_code, len(resp.text), {}

def test_curl_cffi_json_api(impersonate="chrome120"):
    from curl_cffi import requests as curl_requests
    resp = curl_requests.get(
        f"{BASE}/collections/all/products.json",
        params={"limit": 3, "page": 1},
        timeout=30,
        impersonate=impersonate,
    )
    data = {}
    if resp.status_code == 200:
        data = resp.json()
    return resp.status_code, len(resp.text), data

def test_curl_cffi_graphql():
    from curl_cffi import requests as curl_requests
    query = """
    {
      products(first: 3) {
        edges {
          node {
            title
            variants(first: 1) {
              edges {
                node {
                  price
                }
              }
            }
          }
        }
      }
    }
    """
    url = f"{BASE}/api/2026-07/graphql.json"
    resp = curl_requests.post(
        url,
        json={"query": query},
        timeout=30,
        impersonate="chrome120",
    )
    data = {}
    if resp.status_code == 200:
        data = resp.json()
    return resp.status_code, len(resp.text), data

def test_curl_cffi_products_json():
    from curl_cffi import requests as curl_requests
    # Simpler REST endpoint
    url = f"{BASE}/products.json"
    resp = curl_requests.get(
        url,
        params={"limit": 3, "page": 1},
        timeout=30,
        impersonate="chrome120",
    )
    data = {}
    if resp.status_code == 200:
        data = resp.json()
    return resp.status_code, len(resp.text), data

def try_nodriver():
    """Try nodriver (lightweight browser) if available."""
    try:
        import nodriver as nd
    except ImportError:
        return None, None, None, "nodriver not installed"

    import asyncio

    async def _run():
        browser = await nd.start()
        tab = await browser.get(f"{BASE}/collections/all")
        await tab.wait_for_timeout(5000)
        html = await tab.get_content()
        title = await tab.title()
        await browser.stop()
        return title, html

    try:
        title, html = asyncio.run(_run())
        return 200, len(html or ""), {}, f"nodriver: {title[:80] if title else 'no title'}"
    except Exception as e:
        return None, None, None, f"nodriver error: {e}"

def main():
    results = {}

    # Method 1: httpx baseline (current)
    print("\n=== Method A: httpx JSON API (current) ===")
    status, size, data = test_httpx_json_api()
    prods = len(data.get("products", []))
    print(f"  Status: {status}, size: {size} bytes, products: {prods}")
    results["httpx_json_api"] = {"status": status, "size": size, "products": prods}

    if status == 200:
        print("  ✅ httpx already works - no fix needed!")

    # Method 2: curl_cffi JSON API
    print("\n=== Method B: curl_cffi JSON API (Chrome120) ===")
    status, size, data = test_curl_cffi_json_api("chrome120")
    prods = len(data.get("products", []))
    print(f"  Status: {status}, size: {size} bytes, products: {prods}")
    results["curl_cffi_json_chrome120"] = {"status": status, "size": size, "products": prods}
    if status == 200 and prods > 0:
        p = data["products"][0]
        price = p.get("variants", [{}])[0].get("price", "?")
        print(f"  First product: {p.get('title')} - R${price}")

    # Method 3: curl_cffi JSON API (Safari)
    print("\n=== Method C: curl_cffi JSON API (Safari) ===")
    status, size, data = test_curl_cffi_json_api("safari15_5")
    prods = len(data.get("products", []))
    print(f"  Status: {status}, size: {size} bytes, products: {prods}")
    results["curl_cffi_json_safari"] = {"status": status, "size": size, "products": prods}

    # Method 4: curl_cffi GraphQL
    print("\n=== Method D: curl_cffi GraphQL API ===")
    status, size, data = test_curl_cffi_graphql()
    has_data = bool(data.get("data", {}).get("products", {}).get("edges"))
    print(f"  Status: {status}, size: {size} bytes, has products: {has_data}")
    results["curl_cffi_graphql"] = {"status": status, "size": size, "has_products": has_data}
    if has_data:
        edges = data["data"]["products"]["edges"]
        if edges:
            node = edges[0]["node"]
            price = node["variants"]["edges"][0]["node"]["price"]
            print(f"  First product: {node.get('title')} - R${price}")

    # Method 5: curl_cffi /products.json
    print("\n=== Method E: curl_cffi /products.json ===")
    status, size, data = test_curl_cffi_products_json()
    prods = len(data.get("products", []))
    print(f"  Status: {status}, size: {size} bytes, products: {prods}")
    results["curl_cffi_products_json"] = {"status": status, "size": size, "products": prods}

    # Method 6: Nodriver browser (if available)
    print("\n=== Method F: Nodriver browser ===")
    status, size, data, msg = try_nodriver()
    print(f"  Result: {msg}")
    results["nodriver_browser"] = {"status": status, "size": size, "message": str(msg)}

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY - Chefon Bypass Test Results")
    print("=" * 60)
    for method, res in results.items():
        status_str = f"HTTP {res.get('status','?')}" if res.get('status') else "SKIP"
        size_str = f"{res.get('size',0)}b" if res.get('size') else "-"
        prod_str = f"{res.get('products', res.get('has_products', '?'))} prods"
        msg = res.get('message', '')
        ok = res.get('status') == 200
        print(f"  {'✅' if ok else '❌'} {method:35s} {status_str:10s} {size_str:10s} {prod_str} {msg[:60] if msg else ''}")

    # Winner recommendation
    winners = [(m, r) for m, r in results.items() if r.get('status') == 200 and (r.get('products', 0) > 0 or r.get('has_products', False))]
    if winners:
        print(f"\n✅ Winners: {len(winners)} methods work!")
        for m, r in winners:
            print(f"   🏆 {m}: HTTP {r['status']}, {r.get('products', r.get('has_products', '?'))} products")
    else:
        print("\n❌ No method worked!")
        print("   Next steps: Try Nodriver (needs install) or Camoufox")

if __name__ == "__main__":
    main()
