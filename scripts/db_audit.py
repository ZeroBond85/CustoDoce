"""Audit ALL Supabase queries against real database."""

import os
import time

from supabase import create_client

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
errors = []
slow = []


def test(name, fn):
    start = time.time()
    try:
        result = fn()
        elapsed = (time.time() - start) * 1000
        if elapsed > 2000:
            slow.append((name, elapsed))
        return result
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        errors.append((name, str(e)[:120], elapsed))
        return None


def check_columns(table, expected_cols):
    try:
        r = sb.table(table).select("*").limit(1).execute()
    except Exception as e:
        return False, [f"TABLE MISSING: {e}"]
    if not r.data:
        return True, []
    actual = set(r.data[0].keys())
    missing = [c for c in expected_cols if c not in actual]
    return len(missing) == 0, missing


print("=" * 60)
print("1. TABLE EXISTENCE + COLUMN CHECKS")
print("=" * 60)

tables_expected = {
    "prices": [
        "id",
        "ingredient_id",
        "store_id",
        "source",
        "store_name",
        "raw_product",
        "raw_price",
        "raw_unit",
        "collected_at",
        "valid_from",
        "valid_until",
        "confidence",
        "tier",
        "brand",
        "city",
        "logistics",
        "normalized",
    ],
    "price_history": ["id", "price_id", "ingredient_id", "store_id", "collected_at"],
    "review_queue": [
        "id",
        "raw_product",
        "raw_price",
        "raw_unit",
        "store_name",
        "source",
        "confidence",
        "status",
        "resolved_ingredient",
        "brand",
        "image_url",
        "source_url",
        "match_reason",
        "match_type",
        "top3",
    ],
    "ingredients": ["id", "canonical_name", "aliases", "active", "brands", "search_terms"],
    "stores": ["id", "name", "tier", "type", "is_active", "priority"],
    "flyers": ["id", "store_name", "region", "image_url", "image_hash", "ocr_status", "source", "collected_at"],
    "scraping_logs": [
        "id",
        "store_name",
        "status",
        "started_at",
        "finished_at",
        "items_found",
        "items_matched",
        "errors",
    ],
    "schedules": ["id", "name", "enabled"],
    "scrape_frequencies": ["id", "store_id", "tier"],
    "alert_recipients": ["id", "name", "channel", "active"],
    "alert_rules": ["id", "name", "trigger", "enabled"],
    "feature_flags": ["key", "enabled"],
    "recipes": ["id", "name", "created_at"],
    "recipe_items": ["id", "recipe_id", "ingredient_id"],
}

for table, cols in tables_expected.items():
    ok, missing = check_columns(table, cols)
    status = "OK" if ok else f"MISSING: {missing}"
    print(f"  {table:25s} {status}")

print("\n" + "=" * 60)
print("2. RPC FUNCTIONS")
print("=" * 60)

rpcs = [
    (
        "upsert_price_rpc",
        {
            "p_ingredient_id": "__audit_test__",
            "p_store_id": "test",
            "p_source": "test",
            "p_store_name": "test",
            "p_raw_product": "test",
            "p_raw_price": 0,
            "p_raw_unit": "un",
            "p_collected_at": "2099-01-01",
            "p_valid_from": "2099-01-01",
            "p_valid_until": "2099-12-31",
            "p_validity_raw": "",
            "p_collected_weekday": "Seg",
            "p_is_promotion": False,
            "p_tier": 3,
            "p_confidence": 1.0,
            "p_normalized": None,
            "p_city": "",
            "p_logistics": "",
            "p_brand": "",
        },
    ),
    ("cleanup_old_prices", {"retention_days": 9999}),
    ("cleanup_old_logs", {"retention_days": 9999}),
    ("cleanup_old_flyers", {"retention_days": 9999}),
]

for rpc_name, params in rpcs:
    r = test(f"rpc:{rpc_name}", lambda: sb.rpc(rpc_name, params).execute())
    status = "OK" if r is not None else "FAILED"
    print(f"  {rpc_name:30s} {status}")

# Cleanup test data
sb.table("prices").delete().eq("ingredient_id", "__audit_test__").execute()

print("\n" + "=" * 60)
print("3. PRODUCTION QUERIES (key ones)")
print("=" * 60)

queries = [
    ("prices:select_star", lambda: sb.table("prices").select("*").limit(1).execute()),
    (
        "prices:select_by_ingredient",
        lambda: sb.table("prices").select("*").eq("ingredient_id", "Leite Condensado Integral").limit(5).execute(),
    ),
    ("prices:count", lambda: sb.table("prices").select("id", count="exact").limit(1).execute()),
    (
        "prices:order_collected",
        lambda: sb.table("prices").select("*").order("collected_at", desc=True).limit(5).execute(),
    ),
    (
        "prices:index_ingredient",
        lambda: sb.table("prices").select("id").eq("ingredient_id", "Leite Condensado Integral").limit(1).execute(),
    ),
    ("prices:index_store", lambda: sb.table("prices").select("id").eq("store_id", "atacadão").limit(1).execute()),
    (
        "prices:index_collected",
        lambda: sb.table("prices").select("id").order("collected_at", desc=True).limit(1).execute(),
    ),
    (
        "review_queue:select_all",
        lambda: sb.table("review_queue").select("*").order("collected_at", desc=True).limit(10).execute(),
    ),
    (
        "review_queue:count_pending",
        lambda: sb.table("review_queue").select("id", count="exact").eq("status", "pending").limit(1).execute(),
    ),
    ("ingredients:select_all", lambda: sb.table("ingredients").select("*").order("canonical_name").execute()),
    (
        "ingredients:select_active",
        lambda: sb.table("ingredients").select("*").eq("active", True).order("canonical_name").execute(),
    ),
    ("stores:select_all", lambda: sb.table("stores").select("*").order("priority").execute()),
    ("stores:select_active", lambda: sb.table("stores").select("*").eq("is_active", True).order("priority").execute()),
    ("flyers:select_all", lambda: sb.table("flyers").select("*").order("collected_at", desc=True).limit(10).execute()),
    ("flyers:select_pending", lambda: sb.table("flyers").select("*").eq("ocr_status", "pending").limit(5).execute()),
    (
        "scraping_logs:select_all",
        lambda: sb.table("scraping_logs").select("*").order("started_at", desc=True).limit(10).execute(),
    ),
    ("schedules:select_all", lambda: sb.table("schedules").select("*").order("name").execute()),
    ("scrape_frequencies:select_all", lambda: sb.table("scrape_frequencies").select("*").execute()),
    ("alert_recipients:select_all", lambda: sb.table("alert_recipients").select("*").execute()),
    ("alert_rules:select_all", lambda: sb.table("alert_rules").select("*").execute()),
    ("feature_flags:select_all", lambda: sb.table("feature_flags").select("*").order("key").execute()),
    ("recipes:select_all", lambda: sb.table("recipes").select("*").order("created_at", desc=True).limit(10).execute()),
]

for name, fn in queries:
    r = test(name, fn)
    status = "OK" if r is not None else "FAILED"
    count = len(r.data) if r and r.data else 0
    print(f"  {name:40s} {status:6s} ({count} rows)")

print("\n" + "=" * 60)
print("4. DATA INTEGRITY CHECKS")
print("=" * 60)

# Check orphan prices (store_id not in stores)
r_stores = sb.table("stores").select("id").execute()
real_ids = {s["id"] for s in (r_stores.data or [])}

r_prices = sb.table("prices").select("store_id").execute()
orphan_stores = set()
for p in r_prices.data or []:
    sid = p.get("store_id", "")
    if sid and sid not in real_ids:
        orphan_stores.add(sid)

print(f"  Prices with invalid store_id: {len(orphan_stores)} distinct ({', '.join(sorted(orphan_stores)[:5])})")

# Check orphan prices (ingredient_id not in ingredients)
r_ings = sb.table("ingredients").select("canonical_name").execute()
real_ings = {i["canonical_name"] for i in (r_ings.data or [])}

r_prices2 = sb.table("prices").select("ingredient_id").execute()
orphan_ings = set()
for p in r_prices2.data or []:
    iid = p.get("ingredient_id", "")
    if iid and iid not in real_ings:
        orphan_ings.add(iid)

print(f"  Prices with invalid ingredient_id: {len(orphan_ings)} distinct ({', '.join(sorted(orphan_ings)[:5])})")

# Check review_queue consistency
r_rv = sb.table("review_queue").select("status, resolved_ingredient").execute()
approved_no_ing = [i for i in (r_rv.data or []) if i.get("status") == "approved" and not i.get("resolved_ingredient")]
print(f"  Approved reviews without resolved_ingredient: {len(approved_no_ing)}")

# Check flyers without image_url
r_fly = sb.table("flyers").select("id, image_url").execute()
no_img = [f for f in (r_fly.data or []) if not f.get("image_url")]
print(f"  Flyers without image_url: {len(no_img)} / {len(r_fly.data or [])}")

# Check stores referenced in scraping_logs but not in stores
r_logs = sb.table("scraping_logs").select("store_name").execute()
log_stores = set(item.get("store_name", "") for item in (r_logs.data or []) if item.get("store_name"))
r_stores2 = sb.table("stores").select("name").execute()
store_names = set(s["name"] for s in (r_stores2.data or []) if s.get("name"))
missing_in_stores = log_stores - store_names
if missing_in_stores:
    print(f"  Scraping logs reference stores NOT in stores table: {sorted(missing_in_stores)}")
else:
    print("  All scraping log store_names exist in stores table: OK")

print("\n" + "=" * 60)
print("5. PERFORMANCE ISSUES")
print("=" * 60)

# Test full table scans without filters
r_full = test("full_scan:prices", lambda: sb.table("prices").select("id").execute())
print(f"  prices full scan: {len(r_full.data) if r_full and r_full.data else 0} rows")

r_full2 = test("full_scan:flyers", lambda: sb.table("flyers").select("id").execute())
print(f"  flyers full scan: {len(r_full2.data) if r_full2 and r_full2.data else 0} rows")

r_full3 = test("full_scan:scraping_logs", lambda: sb.table("scraping_logs").select("id").execute())
print(f"  scraping_logs full scan: {len(r_full3.data) if r_full3 and r_full3.data else 0} rows")

if errors:
    print("\n" + "=" * 60)
    print("ERRORS")
    print("=" * 60)
    for name, err, ms in errors:
        print(f"  {name:40s} {ms:.0f}ms  {err}")

if slow:
    print("\n" + "=" * 60)
    print("SLOW QUERIES (>2s)")
    print("=" * 60)
    for name, ms in slow:
        print(f"  {name:40s} {ms:.0f}ms")

print("\nDone. Errors: " + str(len(errors)))
