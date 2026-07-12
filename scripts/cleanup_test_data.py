"""
Cleanup test data from Supabase real DB.

Two modes:
  1. remove _test_% rows (pytest autouse fixture covers this, but standalone for safety)
  2. remove rows by timestamp window (for real scrapers that don't tag _test_)

Usage:
    python scripts/cleanup_test_data.py                    # remove _test_% only
    python scripts/cleanup_test_data.py --since TIMESTAMP  # also rows newer than TIMESTAMP
    python scripts/cleanup_test_data.py --all-tables       # include all writable tables
    python scripts/cleanup_test_data.py --dry-run           # show what would be deleted
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")

TABLES = [
    "prices",
    "price_history",
    "review_queue",
    "scraping_logs",
    "flyers",
]


def get_client():
    if not SUPABASE_URL or not SERVICE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required in .env")
        sys.exit(1)
    from supabase import create_client
    return create_client(SUPABASE_URL, SERVICE_KEY)


def _validate_table(name: str) -> str:
    """Whitelist table names to prevent SQL injection via RPC."""
    if name not in TABLES:
        raise ValueError(f"Invalid table: {name}")
    return name


def _validate_iso_timestamp(ts: str) -> str:
    """Validate ISO8601 format to prevent SQL injection."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ts):
        raise ValueError(f"Invalid timestamp format: {ts}")
    return ts


def _count_rows(client, table: str, column: str, pattern: str) -> int:
    """Count rows matching LIKE pattern; returns 0 on error."""
    try:
        q = client.table(table).select("*", count="exact").like(column, pattern).limit(1).execute()
        return q.count if q.count else 0
    except Exception:
        return 0


def _delete_like(client, table: str, column: str, pattern: str) -> int:
    """Delete rows matching LIKE pattern; returns count deleted."""
    try:
        r = client.table(table).delete().like(column, pattern).execute()
        return len(r.data) if r.data else 0
    except Exception as e:
        print(f"[WARN] {table} ({column} LIKE '{pattern}'): {e}")
        return 0


def cleanup_test_prefix(client, dry_run: bool) -> int:
    total = 0
    columns = ["store_name", "raw_product", "ingredient_id"]
    for table in TABLES:
        _validate_table(table)
        found = 0
        for col in columns:
            found += _count_rows(client, table, col, "_test_%")
        if found > 0:
            if dry_run:
                total += found
                print(f"[DRY-RUN] {table}: {found} _test_% rows to delete")
            else:
                deleted = 0
                for col in columns:
                    deleted += _delete_like(client, table, col, "_test_%")
                if deleted > 0:
                    print(f"[DELETED] {table}: {deleted} _test_% rows")
                total += deleted
    return total


def cleanup_by_timestamp(client, since: str, dry_run: bool) -> int:
    ts = _validate_iso_timestamp(since)
    total = 0
    for table in TABLES:
        _validate_table(table)
        try:
            q = client.table(table).select("*", count="exact").gte("created_at", ts).limit(1).execute()
            count = q.count if q.count else 0
            if count > 0:
                if dry_run:
                    total += count
                    print(f"[DRY-RUN] {table}: {count} rows since {ts}")
                else:
                    r = client.table(table).delete().gte("created_at", ts).execute()
                    del_count = len(r.data) if r.data else 0
                    if del_count > 0:
                        print(f"[DELETED] {table}: {del_count} rows since {ts}")
                    total += del_count
        except Exception as e:
            print(f"[WARN] {table} (timestamp): {e}")
    return total


def main():
    parser = argparse.ArgumentParser(description="Cleanup test data from Supabase")
    parser.add_argument("--since", help="Remove rows with created_at >= TIMESTAMP (ISO format)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    args = parser.parse_args()

    print("=== Cleanup Test Data ===")
    if args.dry_run:
        print("DRY-RUN MODE - no data will be deleted")

    client = get_client()
    total = 0

    total += cleanup_test_prefix(client, args.dry_run)

    if args.since:
        total += cleanup_by_timestamp(client, args.since, args.dry_run)

    if total == 0:
        print("No test data found. DB is clean.")
    else:
        print(f"\nTotal rows affected: {total}")


if __name__ == "__main__":
    main()
