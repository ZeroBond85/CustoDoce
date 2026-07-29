"""Phase 6: Full pipeline smoke test - validate all changes."""
import sys
sys.path.insert(0, ".")

from services.collector import load_stores
from scrapers.website_scraper import WebsiteScraper, _HAS_CURL_CFFI

def test_chefon():
    print("=" * 60)
    print("TEST 1: Chefon bypass via curl_cffi")
    print("=" * 60)
    stores = [s for s in load_stores() if s.get("name") == "Chefon"]
    assert stores, "Chefon not found in stores.yaml"
    cfg = stores[0]
    print(f"  Config: shopify_json={cfg.get('shopify_json')}, shopify_curl_cffi={cfg.get('shopify_curl_cffi')}")
    assert cfg.get("shopify_curl_cffi"), "shopify_curl_cffi not enabled in YAML"
    assert _HAS_CURL_CFFI, "curl_cffi not installed"
    scraper = WebsiteScraper(cfg)
    assert scraper.shopify_curl_cffi, "shopify_curl_cffi not enabled in scraper"
    url = f"{scraper.base_url}/collections/all/products.json"
    data = scraper._fetch_shopify_page(url, 1)
    assert data is not None, "Failed to fetch Shopify page"
    prods = data.get("products", [])
    assert len(prods) > 0, f"No products returned: {data}"
    price = prods[0]["variants"][0]["price"]
    print(f"  ✅ Page 1: {len(prods)} products, sample: {prods[0]['title']} - R${price}")
    scraper.close()

def test_tenda_config():
    print()
    print("=" * 60)
    print("TEST 2: Tenda config (vision_timeout_seconds)")
    print("=" * 60)
    stores = [s for s in load_stores() if s.get("name") == "Tenda Atacado"]
    assert stores, "Tenda not found"
    cfg = stores[0]
    tout = cfg.get("vision_timeout_seconds", 300)
    print(f"  vision_timeout_seconds: {tout}")
    assert tout >= 600, f"Expected >= 600, got {tout}"
    print("  ✅ Tenda timeout configured correctly")

def test_roldao_no_false_positive():
    print()
    print("=" * 60)
    print("TEST 3: Roldão - no report_failure on empty OCR")
    print("=" * 60)
    from scrapers.roldao_api_scraper import RoldaoApiScraper
    scraper = RoldaoApiScraper({"name": "Roldão Test"})
    called = []
    scraper.report_failure = lambda **k: called.append(k)
    out = scraper.run([])
    assert out == [], f"Expected empty result, got {out}"
    assert len(called) == 0, f"report_failure was called {len(called)} times: {called}"
    print("  ✅ No report_failure called on empty OCR result")
    scraper.close()

def test_curl_cffi_in_requirements():
    print()
    print("=" * 60)
    print("TEST 4: curl_cffi in requirements")
    print("=" * 60)
    with open("requirements-prod.in") as f:
        content = f.read()
    assert "curl_cffi" in content, "curl_cffi not in requirements-prod.in"
    print("  ✅ curl_cffi in requirements-prod.in")
    with open("requirements.txt", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if "curl_cffi" not in content:
        print("  ⚠️  curl_cffi not in requirements.txt (will be updated on next pip-compile)")
    else:
        print("  ✅ curl_cffi in requirements.txt")

def test_db_cleanup():
    print()
    print("=" * 60)
    print("TEST 5: DB - Bezerra/Promotons deactivated")
    print("=" * 60)
    from services.supabase_client import get_service_client
    client = get_service_client()
    for sid in ["bezerra_embalagens", "promotons"]:
        res = client.table("stores").select("id,is_active").eq("id", sid).execute()
        assert res.data, f"{sid} not found in DB"
        assert not res.data[0]["is_active"], f"{sid} still active!"
        print(f"  ✅ {sid} is inactive")
    # Chefon still active
    res = client.table("stores").select("id,is_active").eq("id", "chefon").execute()
    assert res.data and res.data[0]["is_active"], "Chefon should remain active!"
    print("  ✅ Chefon still active")

def main():
    results = []
    for test in [test_db_cleanup, test_chefon, test_tenda_config, test_roldao_no_false_positive, test_curl_cffi_in_requirements]:
        try:
            test()
            results.append((test.__name__, "✅ PASS"))
        except Exception as e:
            results.append((test.__name__, f"❌ FAIL: {e}"))

    print()
    print("=" * 60)
    print("PHASE 6 SMOKE TEST RESULTS")
    print("=" * 60)
    for name, status in results:
        print(f"  {status} {name}")
    all_pass = all("FAIL" not in s for _, s in results)
    print(f"\n{'✅ ALL TESTS PASSED' if all_pass else '❌ SOME TESTS FAILED'}")

if __name__ == "__main__":
    main()
