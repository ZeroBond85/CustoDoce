"""Compare production DB schema vs expected. Run ALL pending migrations."""
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
            conn = psycopg2.connect(host=host, dbname="postgres", user=user, password=pwd, port=port, connect_timeout=10)
            return conn
        except Exception:
            continue
    raise RuntimeError("Cannot connect to Supabase DB")

conn = get_conn()
cur = conn.cursor()

# 1. List all tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name")
tables = [r[0] for r in cur.fetchall()]
print("=== TABLES IN PRODUCTION ===")
print(", ".join(tables))

# 2. For each table, list columns
expected_columns = {}
# prices
expected_columns['prices'] = ['id','ingredient_id','store_id','source','store_name','raw_product','raw_price','raw_unit','collected_at','valid_from','valid_until','validity_raw','collected_weekday','is_promotion','tier','confidence','normalized','city','logistics','created_at','brand']
# price_history
expected_columns['price_history'] = ['id','price_id','ingredient_id','store_id','store_name','raw_product','raw_price','raw_unit','normalized','valid_from','valid_until','validity_raw','collected_weekday','is_promotion','collected_at','brand']
# review_queue
expected_columns['review_queue'] = ['id','raw_product','raw_price','raw_unit','store_name','source','confidence','suggestions','validity_raw','status','resolved_ingredient','collected_at','reviewed_at','brand','image_url','source_url','match_reason','match_type','top3']
# flyers
expected_columns['flyers'] = ['id','store_name','region','city','flyer_title','flyer_date_start','flyer_date_end','image_url','image_hash','image_type','image_width','image_height','ocr_status','ocr_text','ocr_confidence','products_extracted','source','valid_from','valid_until','collected_at','processed_at']
# stores
expected_columns['stores'] = ['id','name','tier','type','logistics','city','zone','coverage','collection_method','is_active','priority','config','scraper','url_pattern','base_url','api_endpoint','search_url','selectors','publish_day','visit_frequency','contact','created_at','updated_at']

missing_cols = {}
for table, cols in expected_columns.items():
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s", (table,))
    existing = set(r[0] for r in cur.fetchall())
    expected = set(cols)
    missing = expected - existing
    if missing:
        missing_cols[table] = list(missing)

print("\n=== MISSING COLUMNS ===")
if missing_cols:
    for t, cols in missing_cols.items():
        print(f"  {t}: {', '.join(cols)}")
else:
    print("  None!")

# 3. Check if exec_sql function exists
cur.execute("SELECT EXISTS(SELECT 1 FROM pg_proc WHERE proname='exec_sql')")
has_exec_sql = cur.fetchone()[0]
print(f"\n=== exec_sql function exists: {has_exec_sql} ===")

# 4. Check existing functions
cur.execute("SELECT proname FROM pg_proc WHERE pronamespace=(SELECT oid FROM pg_namespace WHERE nspname='public') AND proname NOT LIKE 'pgrst%' ORDER BY proname")
funcs = [r[0] for r in cur.fetchall()]
print(f"Custom functions: {', '.join(funcs) if funcs else 'NONE (missing all!)'}")

cur.close()
conn.close()
