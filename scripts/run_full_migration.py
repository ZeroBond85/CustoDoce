"""Run ALL pending migrations on Supabase production DB."""

import psycopg2
import os

url = os.environ.get("SUPABASE_URL", "")
proj = url.split("//")[1].split(".")[0]
pwd = os.environ.get("SUPABASE_DB_PASSWORD", "")


def get_conn():
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
    raise RuntimeError("Cannot connect to Supabase DB")


conn = get_conn()
cur = conn.cursor()
ok, fail = 0, 0


def run(sql):
    global ok, fail
    try:
        cur.execute(sql)
        conn.commit()
        ok += 1
        print(f"  OK: {sql[:80]}...")
    except Exception as e:
        conn.rollback()
        fail += 1
        print(f"  FAIL: {sql[:60]}...  {e}")


# ─── 1. Create exec_sql function (for future deploy_database.py) ───
print("\n=== 1. exec_sql function ===")
run("""
CREATE OR REPLACE FUNCTION exec_sql(sql text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    EXECUTE sql;
END;
$$;
""")

# ─── 2. Missing stores columns (Phase 5) ───
print("\n=== 2. Stores scraper columns ===")
run("ALTER TABLE stores ADD COLUMN IF NOT EXISTS scraper text;")
run("ALTER TABLE stores ADD COLUMN IF NOT EXISTS url_pattern text;")
run("ALTER TABLE stores ADD COLUMN IF NOT EXISTS base_url text;")
run("ALTER TABLE stores ADD COLUMN IF NOT EXISTS api_endpoint text;")
run("ALTER TABLE stores ADD COLUMN IF NOT EXISTS search_url text;")
run("ALTER TABLE stores ADD COLUMN IF NOT EXISTS selectors jsonb default '{}';")
run("ALTER TABLE stores ADD COLUMN IF NOT EXISTS publish_day text;")
run("ALTER TABLE stores ADD COLUMN IF NOT EXISTS visit_frequency text;")
run("ALTER TABLE stores ADD COLUMN IF NOT EXISTS contact text;")

# ─── 3. Missing cleanup functions ───
print("\n=== 3. Cleanup functions ===")
run("""
CREATE OR REPLACE FUNCTION cleanup_old_prices(retention_days int DEFAULT 90)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM price_history WHERE collected_at < now() - (retention_days || ' days')::interval;
    DELETE FROM prices WHERE collected_at < now() - (retention_days || ' days')::interval;
END;
$$;
""")
run("""
CREATE OR REPLACE FUNCTION cleanup_old_logs(retention_days int DEFAULT 30)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM scraping_logs WHERE started_at < now() - (retention_days || ' days')::interval;
END;
$$;
""")

# ─── 4. Phase 2 updates (already have IF NOT EXISTS, safe to re-run) ───
print("\n=== 4. Phase 2 validity/promotion columns (safe re-run) ===")
run("ALTER TABLE prices ADD COLUMN IF NOT EXISTS valid_from DATE DEFAULT CURRENT_DATE;")
run("ALTER TABLE prices ADD COLUMN IF NOT EXISTS validity_raw TEXT DEFAULT '';")
run("ALTER TABLE prices ADD COLUMN IF NOT EXISTS collected_weekday TEXT DEFAULT '';")
run("ALTER TABLE prices ADD COLUMN IF NOT EXISTS is_promotion BOOLEAN DEFAULT FALSE;")
run("ALTER TABLE price_history ADD COLUMN IF NOT EXISTS valid_from DATE DEFAULT CURRENT_DATE;")
run("ALTER TABLE price_history ADD COLUMN IF NOT EXISTS valid_until DATE DEFAULT (CURRENT_DATE + INTERVAL '7 days');")
run("ALTER TABLE price_history ADD COLUMN IF NOT EXISTS validity_raw TEXT DEFAULT '';")
run("ALTER TABLE price_history ADD COLUMN IF NOT EXISTS collected_weekday TEXT DEFAULT '';")
run("ALTER TABLE price_history ADD COLUMN IF NOT EXISTS is_promotion BOOLEAN DEFAULT FALSE;")
run("ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS validity_raw TEXT DEFAULT '';")
run("ALTER TABLE flyers ADD COLUMN IF NOT EXISTS valid_from DATE;")
run("ALTER TABLE flyers ADD COLUMN IF NOT EXISTS valid_until DATE;")

# ─── 5. Brand column (safe re-run) ───
print("\n=== 5. Brand columns (safe re-run) ===")
run("ALTER TABLE prices ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT '';")
run("ALTER TABLE price_history ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT '';")
run("ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT '';")

print(f"\n{'=' * 50}")
print(f"Migration complete: {ok} OK, {fail} FAIL")
cur.close()
conn.close()
