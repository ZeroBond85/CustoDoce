#!/usr/bin/env python3
"""
CustoDoce — Database Deployment Script

Combines all SQL migrations into a single executable script.
Handles stores table conflict gracefully using DO $$ blocks.

Usage:
    python scripts/deploy_database.py                # Generate consolidated.sql
    python scripts/deploy_database.py --execute       # Execute via Supabase client
    python scripts/deploy_database.py --output FILE   # Write consolidated SQL to FILE
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO_ROOT = Path(__file__).resolve().parent.parent


def generate_consolidated() -> str:
    gen = []

    # ─── 1. seed.sql — Core tables ───────────────────────────────
    gen.append("-- ============================================================")
    gen.append("-- PHASE 1: Core tables (seed.sql)")
    gen.append("-- ============================================================")

    seed_path = REPO_ROOT / "supabase_sql" / "seed.sql"
    if seed_path.exists():
        gen.append(seed_path.read_text(encoding="utf-8"))

    # ─── 2. migration_vigencia.sql — Columns + triggers ──────────
    gen.append("\n-- ============================================================")
    gen.append("-- PHASE 2: Validity/promotion columns (migration_vigencia.sql)")
    gen.append("-- ============================================================")

    vigencia_path = REPO_ROOT / "supabase_sql" / "migration_vigencia.sql"
    if vigencia_path.exists():
        gen.append(vigencia_path.read_text(encoding="utf-8"))

    # ─── 3. 001_config_tables.sql — Config tables (adapted) ────
    gen.append("\n-- ============================================================")
    gen.append("-- PHASE 3: Config tables (001_config_tables.sql, adapted)")
    gen.append("-- ============================================================")

    config_path = REPO_ROOT / "supabase" / "migrations" / "001_config_tables.sql"
    if config_path.exists():
        raw = config_path.read_text(encoding="utf-8")
        lines = raw.split("\n")
        filtered = []
        skip_until_empty = False
        for line in lines:
            s = line.strip().lower()
            # Skip CREATE TABLE IF NOT EXISTS stores (already exists from seed.sql)
            if "create table if not exists stores" in s:
                filtered.append("-- SKIPPED: stores table already exists from seed.sql")
                skip_until_empty = True
                continue
            # Skip CREATE TABLE IF NOT EXISTS scrape_frequencies (FK to stores UUID)
            if "create table if not exists scrape_frequencies" in s:
                filtered.append("-- SKIPPED: scrape_frequencies depends on stores UUID PK")
                skip_until_empty = True
                continue
            # End skip when we hit a DDL statement or empty line
            if skip_until_empty:
                if s == "" or s.startswith("--") or s.startswith("create ") or s.startswith("alter ") or s.startswith("grant ") or s.startswith("drop "):
                    skip_until_empty = False
                    if not s.startswith("--") and s != "":
                        filtered.append(line)
                continue
            filtered.append(line)

        # Wrap index/trigger on stores(scraper) in safe DO block
        cleaned = "\n".join(filtered)
        cleaned = cleaned.replace(
            "create index if not exists idx_stores_scraper on stores(scraper);",
            "DO $$ BEGIN\n"
            "    IF EXISTS (SELECT 1 FROM information_schema.columns\n"
            "               WHERE table_name='stores' AND column_name='scraper') THEN\n"
            "        CREATE INDEX IF NOT EXISTS idx_stores_scraper ON stores(scraper);\n"
            "    END IF;\n"
            "END $$;"
        )
        gen.append(cleaned)

    # ─── 4. Cleanup function ─────────────────────────────────────
    gen.append("\n-- ============================================================")
    gen.append("-- PHASE 4: Cleanup function (TTL)")
    gen.append("-- ============================================================")
    gen.append("""
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

    # ─── 5. Add scraper column to stores if missing ──────────────
    gen.append("""
-- ============================================================
-- PHASE 5: Adapt stores table (add missing 001_config columns)
-- ============================================================
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='scraper') THEN
        ALTER TABLE stores ADD COLUMN scraper text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='url_pattern') THEN
        ALTER TABLE stores ADD COLUMN url_pattern text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='base_url') THEN
        ALTER TABLE stores ADD COLUMN base_url text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='api_endpoint') THEN
        ALTER TABLE stores ADD COLUMN api_endpoint text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='search_url') THEN
        ALTER TABLE stores ADD COLUMN search_url text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='selectors') THEN
        ALTER TABLE stores ADD COLUMN selectors jsonb default '{}';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='publish_day') THEN
        ALTER TABLE stores ADD COLUMN publish_day text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='visit_frequency') THEN
        ALTER TABLE stores ADD COLUMN visit_frequency text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='contact') THEN
        ALTER TABLE stores ADD COLUMN contact text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stores' AND column_name='priority') THEN
        ALTER TABLE stores ADD COLUMN priority int default 99;
    END IF;
END $$;
""")

    # ─── 6. Add brand column to prices/price_history/review_queue ──
    gen.append("""
-- ============================================================
-- PHASE 6: Add brand column (002_add_brand_column.sql)
-- ============================================================
ALTER TABLE prices ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT '';
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT '';
""")

    gen.append("\n-- ============================================================")
    gen.append("-- Migration complete. Verify with:")
    gen.append("--   SELECT table_name FROM information_schema.tables")
    gen.append("--   WHERE table_schema = 'public' ORDER BY table_name;")
    gen.append("-- ============================================================")

    return "\n".join(gen)


def main():
    parser = argparse.ArgumentParser(description="Deploy CustoDoce database schema")
    parser.add_argument("--execute", action="store_true", help="Execute SQL on Supabase")
    parser.add_argument("--output", type=str, help="Write consolidated SQL to file")
    args = parser.parse_args()

    sql = generate_consolidated()
    total_tables = 12  # prices, price_history, review_queue, scraping_logs, stores, flyers, ingredients, schedules, scrape_frequencies, alert_recipients, alert_rules, feature_flags

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(sql, encoding="utf-8")
        print(f"Consolidated SQL written to: {out_path}")
        print(f"Size: {len(sql)} bytes, ~{len(sql.split(chr(10)))} lines")
        print(f"Expected tables after migration: {total_tables}")
        print("\nNext step: Paste the content of this file into Supabase SQL Editor and run.")
        return

    if args.execute:
        print("Executing migrations on Supabase...")
        try:
            from services.supabase_client import get_service_client
            client = get_service_client()
        except Exception as e:
            print(f"ERROR: Cannot connect to Supabase: {e}")
            print("Make sure SUPABASE_URL and SUPABASE_SERVICE_KEY are set in .env")
            sys.exit(1)

        # Split into statements and execute each one
        statements = []
        current = []
        for line in sql.split("\n"):
            current.append(line)
            if line.strip().endswith(";"):
                statements.append("\n".join(current))
                current = []
        if current:
            stmt = "\n".join(current).strip()
            if stmt and not stmt.startswith("--"):
                statements.append(stmt)

        ok, fail = 0, 0
        for stmt in statements:
            if not stmt.strip() or stmt.strip().startswith("--"):
                continue
            try:
                client.postgrest.rpc("exec_sql", {"sql": stmt.strip()}).execute()
                ok += 1
            except Exception as e:
                err = str(e)[:120]
                print(f"  WARN: {err}")
                fail += 1

        print(f"\nMigration complete: {ok} OK, {fail} WARN")
        print(f"Expected tables: {total_tables}")
        print("Verify in Supabase Dashboard > Database > Tables")
        return

    # Default: print to stdout
    print(sql)


if __name__ == "__main__":
    main()
