import psycopg2, os
url = os.environ.get("SUPABASE_URL", "")
proj = url.split("//")[1].split(".")[0]
pwd = os.environ.get("SUPABASE_DB_PASSWORD", "")
for host, port, user in [
    (f"db.{proj}.supabase.co", 5432, "postgres"),
    (f"aws-0-us-west-1.pooler.supabase.com", 6543, f"postgres.{proj}"),
]:
    try:
        print(f"Trying {host}:{port} as {user}...")
        conn = psycopg2.connect(host=host, dbname="postgres", user=user, password=pwd, port=port, connect_timeout=10)
        print("Connected!")
        break
    except Exception as e:
        print(f"  Failed: {e}")
else:
    print("All connection attempts failed!")
    exit(1)
cur = conn.cursor()
for t in ["prices", "price_history", "review_queue"]:
    sql = f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT ''"
    cur.execute(sql)
    print(f"OK: {t}")
conn.commit()
cur.close()
conn.close()
print("Migration complete!")
