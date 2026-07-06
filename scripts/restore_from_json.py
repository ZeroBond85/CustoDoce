#!/usr/bin/env python3
"""
Restore CustoDoce database from JSON backup via Supabase RPC (port 443).
Works in CI/CD where port 5432 is blocked.

Usage:
    python scripts/restore_from_json.py backup.json.gz --dry-run
    python scripts/restore_from_json.py backup.json.gz --execute
"""

import argparse
import gzip
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from supabase import create_client

TABLE_ORDER = [
    "ingredients",
    "stores",
    "alert_recipients",
    "schedules",
    "scrape_frequencies",
    "alert_rules",
    "feature_flags",
    "recipes",
    "flyers",
    "prices",
    "price_history",
    "review_queue",
    "scraping_logs",
    "llm_match_cache",
    "scraper_health_log",
    "recipe_items",
]


def load_backup(filepath: str) -> dict:
    """Load and validate backup JSON."""
    with gzip.open(filepath, "rt", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Backup root must be a JSON object with table names as keys")

    missing = [t for t in TABLE_ORDER if t not in data]
    if missing:
        print(f"WARNING: Missing tables in backup: {missing}")

    return data


def dry_run_check(client, table: str, rows: list) -> dict:
    """Simulate insert by checking if table exists and columns match."""
    result: dict = {"table": table, "rows": len(rows), "status": "OK", "details": []}

    # Check table exists via RPC
    try:
        # ruff: noqa: S608
        check = client.rpc(
            "exec_sql_query",
            {
                "sql": f"SELECT COUNT(*) FROM {table} LIMIT 1",
            },
        ).execute()
        result["details"].append(f"Table exists: {check.data}")  # type: ignore
    except Exception as e:
        result["status"] = "WARN"
        result["details"].append(f"Table check failed: {e}")  # type: ignore

    # Sample first row structure
    if rows:
        sample = rows[0]
        result["details"].append(f"Sample columns: {list(sample.keys())}")  # type: ignore
        result["details"].append(f"Sample row: {json.dumps(sample, default=str)[:200]}")  # type: ignore

    return result


def execute_restore(client, table: str, rows: list, dry_run: bool) -> dict:
    """Insert rows via Supabase client (uses REST API on port 443)."""
    if dry_run:
        return dry_run_check(client, table, rows)

    result: dict = {"table": table, "rows": len(rows), "status": "OK", "inserted": 0, "errors": []}

    if not rows:
        result["details"] = ["No rows to insert"]
        return result

    # Batch insert in chunks of 100
    chunk_size = 100
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        try:
            resp = client.table(table).upsert(chunk, on_conflict="id").execute()
            result["inserted"] += len(resp.data) if resp.data else 0  # type: ignore
        except Exception:
            # Try without on_conflict for tables without id
            try:
                resp = client.table(table).insert(chunk).execute()
                result["inserted"] += len(resp.data) if resp.data else 0  # type: ignore
            except Exception as e2:
                result["status"] = "ERROR"
                result["errors"].append(f"Chunk {i // chunk_size}: {e2}")  # type: ignore

    return result


def main():
    parser = argparse.ArgumentParser(description="Restore CustoDoce DB from JSON backup via RPC")
    parser.add_argument("backup_file", help="Path to .json.gz backup file")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Validate only, no data changes")
    group.add_argument("--execute", action="store_true", help="Actually restore data")
    parser.add_argument("--tables", nargs="+", help="Specific tables to restore (default: all)")
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
        sys.exit(1)

    print(f"Loading backup from {args.backup_file}...")
    backup = load_backup(args.backup_file)

    client = create_client(url, key)
    print("Connected to Supabase via REST API (port 443)")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'EXECUTE'}")
    print(f"Tables in backup: {list(backup.keys())}")

    tables_to_process = args.tables if args.tables else TABLE_ORDER
    tables_to_process = [t for t in tables_to_process if t in backup]

    print(f"\nProcessing {len(tables_to_process)} tables...")
    print("-" * 60)

    all_results = []
    total_rows = 0
    total_inserted = 0

    for table in tables_to_process:
        rows = backup.get(table, [])
        total_rows += len(rows)
        print(f"\n[{table}] {len(rows)} rows")

        result = execute_restore(client, table, rows, args.dry_run)
        all_results.append(result)

        if result["status"] == "OK":
            print(f"  OK - {'would insert' if args.dry_run else 'inserted'} {result.get('inserted', len(rows))} rows")
        else:
            print(f"  {result['status']} - {result.get('errors', result.get('details', []))}")

        if not args.dry_run:
            total_inserted += result.get("inserted", 0)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'EXECUTE'}")
    print(f"Tables processed: {len(all_results)}")
    print(f"Total rows in backup: {total_rows}")
    if not args.dry_run:
        print(f"Total rows inserted: {total_inserted}")

    failed = [r for r in all_results if r["status"] != "OK"]
    if failed:
        print(f"\nFAILED TABLES ({len(failed)}):")
        for r in failed:
            print(f"  {r['table']}: {r.get('errors', r.get('details'))}")
        sys.exit(1)
    else:
        print("\nALL TABLES OK")
        if args.dry_run:
            print("Run with --execute to perform actual restore")


if __name__ == "__main__":
    main()
