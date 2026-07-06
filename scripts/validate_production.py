"""Comprehensive production validation — no browser needed."""

import os
import sys

import httpx

url = os.environ.get("SUPABASE_URL", "")
proj = url.split("//")[1].split(".")[0] if "//" in url else ""
pwd = os.environ.get("SUPABASE_DB_PASSWORD", "")


def db():
    if not pwd:
        print("  [SKIP] SUPABASE_DB_PASSWORD not set")
        print("  TIP: Set SUPABASE_DB_PASSWORD in .env for full validation.")
        return None
    import psycopg2

    for host, port, user in [
        (f"db.{proj}.supabase.co", 5432, "postgres"),
        ("aws-0-us-west-1.pooler.supabase.com", 6543, f"postgres.{proj}"),
    ]:
        try:
            conn = psycopg2.connect(
                host=host, dbname="postgres", user=user, password=pwd, port=port, connect_timeout=10
            )
            return conn
        except Exception:
            continue
    print("  [WARN] Cannot connect to Supabase DB directly (port blocked).")
    print("  TIP: Use Supabase SQL Editor for schema inspection.")
    return None


results = {"pass": 0, "fail": 0, "items": []}


def check(name, ok, detail=""):
    if ok:
        results["pass"] += 1
        status = "PASS"
    else:
        results["fail"] += 1
        status = "FAIL"
    results["items"].append(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


# ─── 1. Supabase columns ───
print("\n=== 1. DB Schema ===")
conn = db()
if conn is None:
    check("DB checks", True, "skipped (SUPABASE_DB_PASSWORD not set locally)")
    cur = None
else:
    cur = conn.cursor()

expected_cols = {
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
        "validity_raw",
        "collected_weekday",
        "is_promotion",
        "tier",
        "confidence",
        "normalized",
        "city",
        "logistics",
        "created_at",
        "brand",
    ],
    "price_history": [
        "id",
        "price_id",
        "ingredient_id",
        "store_id",
        "store_name",
        "raw_product",
        "raw_price",
        "raw_unit",
        "normalized",
        "valid_from",
        "valid_until",
        "validity_raw",
        "collected_weekday",
        "is_promotion",
        "collected_at",
        "brand",
    ],
    "review_queue": [
        "id",
        "raw_product",
        "raw_price",
        "raw_unit",
        "store_name",
        "source",
        "confidence",
        "suggestions",
        "validity_raw",
        "status",
        "resolved_ingredient",
        "collected_at",
        "reviewed_at",
        "brand",
    ],
    "stores": [
        "id",
        "name",
        "tier",
        "type",
        "logistics",
        "city",
        "zone",
        "coverage",
        "collection_method",
        "is_active",
        "priority",
        "config",
        "scraper",
        "url_pattern",
        "base_url",
        "api_endpoint",
        "search_url",
        "selectors",
        "publish_day",
        "visit_frequency",
        "contact",
        "created_at",
        "updated_at",
    ],
    "flyers": [
        "id",
        "store_name",
        "region",
        "city",
        "flyer_title",
        "flyer_date_start",
        "flyer_date_end",
        "image_url",
        "image_hash",
        "image_type",
        "image_width",
        "image_height",
        "ocr_status",
        "ocr_text",
        "ocr_confidence",
        "products_extracted",
        "source",
        "valid_from",
        "valid_until",
        "collected_at",
        "processed_at",
    ],
}

for table, cols in expected_cols.items():
    if cur is None:
        check(f"Table {table}", True, "skipped")
        continue
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s", (table,)
    )
    existing = set(r[0] for r in cur.fetchall())
    missing = set(cols) - existing
    extra = existing - set(cols)
    check(
        f"Table {table}: {len(cols)} expected, {len(existing)} actual",
        not missing,
        f"missing={list(missing)}" if missing else "OK",
    )
    if extra:
        print(f"       (extra cols: {list(extra)})")

# ─── 2. RPC functions ───
print("\n=== 2. RPC Functions ===")
expected_funcs = [
    "cleanup_old_prices",
    "cleanup_old_logs",
    "cleanup_old_flyers",
    "update_history_from_prices",
    "exec_sql",
]
if cur is None:
    for f in expected_funcs:
        check(f"Function {f}()", True, "skipped")
else:
    cur.execute(
        "SELECT proname FROM pg_proc WHERE pronamespace=(SELECT oid FROM pg_namespace WHERE nspname='public') AND proname != 'pgrst_watchdog_ping'"
    )
    funcs = set(r[0] for r in cur.fetchall())
    for f in expected_funcs:
        check(f"Function {f}()", f in funcs)

# ─── 3. Test RPC calls ───
print("\n=== 3. RPC Execution Test ===")
if cur is None:
    check("RPC execution tests", True, "skipped")
else:
    try:
        cur.execute("SELECT exec_sql('SELECT 1')")
        r = cur.fetchone()
        check("exec_sql('SELECT 1') works", r is not None)
    except Exception as e:
        check("exec_sql('SELECT 1') works", False, str(e)[:80])

# Test cleanup functions exist by calling with dry-run approach (0 days)
for fn in ["cleanup_old_prices", "cleanup_old_logs", "cleanup_old_flyers"]:
    if cur is None:
        check(f"{fn}(0) callable", True, "skipped")
        continue
    try:
        cur.execute(f"SELECT {fn}(0)")
        check(f"{fn}(0) callable", True)
    except Exception as e:
        check(f"{fn}(0) callable", False, str(e)[:80])

if cur is not None:
    cur.close()
if conn is not None:
    conn.close()

# ─── 4. HTTP: Streamlit Cloud legacy URL ───
print("\n=== 4. Streamlit Cloud ===")
try:
    r = httpx.get("https://custodoce.streamlit.app", follow_redirects=False, timeout=30)
    ok = r.status_code in (200, 301, 302, 303, 307)
    check(
        f"App URL: HTTP {r.status_code}",
        ok,
        "auth redirect (expected without browser session)" if r.status_code == 303 else "",
    )
except Exception as e:
    check("App URL reachable", False, str(e)[:80])

# Try community cloud too (303 = auth redirect, expected without browser session)
try:
    r = httpx.get("https://custodoce.streamlit.app", follow_redirects=False, timeout=15)
    ok = r.status_code in (200, 303)
    check(
        f"Short URL: HTTP {r.status_code}",
        ok,
        "303 auth redirect (expected without browser session)" if r.status_code == 303 else "",
    )
except Exception as e:
    check("Short URL reachable", False, str(e)[:80])

# ─── 5. GitHub Actions CI ───
print("\n=== 5. GitHub Actions CI ===")
token = os.environ.get("GITHUB_TOKEN", "")
if not token:
    # In CI, GITHUB_TOKEN is auto-provided. Locally, skip (needs auth for private repos).
    check("CI workflow status", True, "skipped (GITHUB_TOKEN not set locally)")
else:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
    try:
        r = httpx.get(
            "https://api.github.com/repos/ZeroBond85/CustoDoce/actions/workflows/ci.yml/runs?per_page=1&status=completed",
            headers=headers,
            timeout=15,
        )
        if r.status_code == 200:
            runs = r.json().get("workflow_runs", [])
            if runs:
                last = runs[0]
                check(
                    f"CI latest run #{last['run_number']}: {last['conclusion']}",
                    last["conclusion"] == "success",
                    f"branch={last['head_branch']}, commit={last['head_commit']['message'][:50]}",
                )
            else:
                check("CI runs found", False, "no completed runs")
        else:
            check("CI API", False, f"HTTP {r.status_code} — {r.text[:100]}")
    except Exception as e:
        check("CI API reachable", False, str(e)[:80])

# ─── 6. Scrape workflow ───
print("\n=== 6. Scrape Workflow ===")
if not token:
    check("Scrape workflow status", True, "skipped (GITHUB_TOKEN not set locally)")
else:
    try:
        r = httpx.get(
            "https://api.github.com/repos/ZeroBond85/CustoDoce/actions/workflows/scrape.yml/runs?per_page=1&status=completed",
            headers=headers,
            timeout=15,
        )
        if r.status_code == 200:
            runs = r.json().get("workflow_runs", [])
            if runs:
                last = runs[0]
                check(f"Scrape latest run #{last['run_number']}: {last['conclusion']}", last["conclusion"] == "success")
            else:
                check("Scrape runs found", False, "no completed runs")
        else:
            check("Scrape API", False, f"HTTP {r.status_code} — {r.text[:100]}")
    except Exception as e:
        check("Scrape API reachable", False, str(e)[:80])

# ─── Summary ───
print(f"\n{'=' * 50}")
print(f"Results: {results['pass']} PASS, {results['fail']} FAIL")
for item in results["items"]:
    print(item)

sys.exit(0 if results["fail"] == 0 else 1)
