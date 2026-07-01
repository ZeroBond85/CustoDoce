"""RPC-based backup via Supabase REST API (port 443).
Fallback when pg_dump fails (port 5432 blocked in CI).

Usage:
    python scripts/rpc_backup.py [--schema]
"""

import json
import gzip
import datetime
import os
import argparse

from supabase import create_client


ALL_TABLES = [
    "prices",
    "price_history",
    "review_queue",
    "stores",
    "ingredients",
    "flyers",
    "scrape_frequencies",
    "alert_rules",
    "feature_flags",
    "scraper_health_log",
    "llm_match_cache",
    "recipes",
    "recipe_items",
    "schedules",
    "alert_recipients",
    "scraping_logs",
]


def run_backup(include_schema: bool = False):
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    s = create_client(url, key)

    backup: dict[str, dict[str, list]] = {"data": {}, "schema": {}}

    for t in ALL_TABLES:
        try:
            data = s.table(t).select("*").execute().data
            backup["data"][t] = data if data is not None else []
            print(f"  {t}: {len(data) if data else 0} rows")
        except Exception as e:
            print(f"  {t}: ERROR {e}")
            backup["data"][t] = []

    if include_schema:
        print("Dumping schema via exec_sql_query RPC...")
        try:
            schema_sql = """
            SELECT
                table_name,
                column_name,
                data_type,
                is_nullable,
                column_default,
                ordinal_position
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position;
            """
            result = s.rpc("exec_sql_query", {"sql": schema_sql}).execute()
            backup["schema"]["columns"] = list(result.data) if result.data is not None else []  # type: ignore[arg-type]

            idx_sql = """
            SELECT
                schemaname,
                tablename,
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
            ORDER BY tablename, indexname;
            """
            result = s.rpc("exec_sql_query", {"sql": idx_sql}).execute()
            backup["schema"]["indexes"] = list(result.data) if result.data is not None else []  # type: ignore[arg-type]

            const_sql = """
            SELECT
                tc.table_name,
                tc.constraint_name,
                tc.constraint_type,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints tc
            LEFT JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            LEFT JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.table_schema = 'public'
            ORDER BY tc.table_name, tc.constraint_name;
"""
            result = s.rpc("exec_sql_query", {"sql": const_sql}).execute()
            backup["schema"]["constraints"] = list(result.data) if result.data is not None else []  # type: ignore[arg-type]

            trig_sql = """
            SELECT
                trigger_name,
                event_manipulation,
                event_object_table,
                action_statement,
                action_timing
            FROM information_schema.triggers
            WHERE trigger_schema = 'public'
            ORDER BY event_object_table, trigger_name;
            """
            result = s.rpc("exec_sql_query", {"sql": trig_sql}).execute()
            backup["schema"]["triggers"] = list(result.data) if result.data is not None else []  # type: ignore[arg-type]

            func_sql = """
            SELECT
                p.proname AS function_name,
                pg_get_functiondef(p.oid) AS definition
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE n.nspname = 'public'
            ORDER BY p.proname;
            """
            result = s.rpc("exec_sql_query", {"sql": func_sql}).execute()
            backup["schema"]["functions"] = list(result.data) if result.data is not None else []  # type: ignore[arg-type]

            print("  schema: dumped (columns, indexes, constraints, triggers, functions)")
        except Exception as e:
            print(f"  schema: ERROR {e}")
            backup["schema"] = {}

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", action="store_true", help="Include schema dump")
    args = parser.parse_args()
    run_backup(include_schema=args.schema)