"""RPC-based backup via Supabase REST API (porta 443).
Fallback quando pg_dump falha (porta 5432 bloqueada no CI).

Usage:
    python scripts/rpc_backup.py
"""
import json
import gzip
import datetime
import os

from supabase import create_client


def run_backup():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    s = create_client(url, key)

    tables = [
        "prices", "price_history", "review_queue", "stores",
        "ingredients", "flyers", "scrape_frequencies", "alert_rules",
        "feature_flags",
    ]
    backup = {}
    for t in tables:
        try:
            data = s.table(t).select("*").execute().data
            backup[t] = data
            print(f"  {t}: {len(data)} rows")
        except Exception as e:
            print(f"  {t}: ERROR {e}")

    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fn = f"custodoce_backup_rpc_{ts}.json.gz"
    with gzip.open(fn, "wt", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, default=str)
    print(f"Wrote {fn}")

    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a") as f:
            f.write(f"filename={fn}\n")
            f.write(f"timestamp={ts}\n")

    return fn


if __name__ == "__main__":
    run_backup()
