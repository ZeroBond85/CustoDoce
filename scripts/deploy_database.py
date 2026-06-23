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
import os
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
            # Skip CREATE TABLE scrape_frequencies (UUID PK → TEXT PK mismatch)
            # and insert the corrected CREATE TABLE so later Phase 3 refs work
            if "create table if not exists scrape_frequencies" in s:
                filtered.append("-- REPLACED: scrape_frequencies with TEXT PK (original used UUID)")
                filtered.append(
                    "CREATE TABLE IF NOT EXISTS scrape_frequencies ("
                    "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
                    "store_id TEXT REFERENCES stores(id) ON DELETE CASCADE,"
                    "tier INT,"
                    "frequency_minutes INT DEFAULT 1440,"
                    "max_retries INT DEFAULT 2,"
                    "timeout_seconds INT DEFAULT 30,"
                    "rate_limit_per_minute INT DEFAULT 10,"
                    "enabled BOOLEAN DEFAULT TRUE,"
                    "created_at TIMESTAMPTZ DEFAULT NOW(),"
                    "updated_at TIMESTAMPTZ DEFAULT NOW()"
                    ");"
                )
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

    gen.append("""
-- ============================================================
-- PHASE 7: Ensure UNIQUE constraint on prices + price_history
-- (Fix 42P10 error when approving review queue items)
-- ============================================================
-- Remove exact duplicates before adding constraint (keep 1 row per exact match)
DELETE FROM prices p1 USING (
    SELECT ingredient_id, store_id, collected_at, MIN(ctid) AS keep_ctid
    FROM prices
    GROUP BY ingredient_id, store_id, collected_at
    HAVING COUNT(*) > 1
) p2
WHERE p1.ingredient_id = p2.ingredient_id
  AND p1.store_id = p2.store_id
  AND p1.collected_at = p2.collected_at
  AND p1.ctid <> p2.keep_ctid;

DELETE FROM price_history ph1 USING (
    SELECT ingredient_id, store_id, collected_at, MIN(ctid) AS keep_ctid
    FROM price_history
    GROUP BY ingredient_id, store_id, collected_at
    HAVING COUNT(*) > 1
) ph2
WHERE ph1.ingredient_id = ph2.ingredient_id
  AND ph1.store_id = ph2.store_id
  AND ph1.collected_at = ph2.collected_at
  AND ph1.ctid <> ph2.keep_ctid;

-- Drop the old 2-column constraint if it still exists
ALTER TABLE prices DROP CONSTRAINT IF EXISTS prices_ingredient_id_store_id_key;
ALTER TABLE price_history DROP CONSTRAINT IF EXISTS price_history_ingredient_id_store_id_key;

-- Add the 3-column constraint (safe: skip if already exists)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'prices'::regclass
        AND conname = 'prices_ingredient_id_store_id_collected_at_key'
    ) THEN
        ALTER TABLE prices
        ADD CONSTRAINT prices_ingredient_id_store_id_collected_at_key
        UNIQUE (ingredient_id, store_id, collected_at);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'price_history'::regclass
        AND conname = 'price_history_ingredient_id_store_id_collected_at_key'
    ) THEN
        ALTER TABLE price_history
        ADD CONSTRAINT price_history_ingredient_id_store_id_collected_at_key
        UNIQUE (ingredient_id, store_id, collected_at);
    END IF;
END $$;

-- ============================================================
-- PHASE 8: scrape_frequencies indexes + RLS (table already created in Phase 3)
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_scrape_freq_store ON scrape_frequencies(store_id);
CREATE INDEX IF NOT EXISTS idx_scrape_freq_tier ON scrape_frequencies(tier);
CREATE INDEX IF NOT EXISTS idx_scrape_freq_enabled ON scrape_frequencies(enabled);

ALTER TABLE scrape_frequencies ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON scrape_frequencies FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "anon_read" ON scrape_frequencies FOR SELECT USING (true);
""")

    gen.append("""
-- ============================================================
-- PHASE 9: Add review_queue columns (image_url, source_url, match_reason, match_type)
-- ============================================================
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS image_url TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS source_url TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS match_reason TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS match_type TEXT DEFAULT '';
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS top3 JSONB DEFAULT '[]';
""")

    gen.append("""
-- ============================================================
-- PHASE 10: Performance indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_prices_ing_collected ON prices(ingredient_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_ing_collected ON price_history(ingredient_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_collected ON review_queue(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_stores_name ON stores(name);
CREATE INDEX IF NOT EXISTS idx_logs_store_started ON scraping_logs(store_name, started_at DESC);
""")

    gen.append("""
-- ============================================================
-- PHASE 11: Add brands + search_terms to ingredients
-- ============================================================
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS brands TEXT[] DEFAULT '{}';
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS search_terms TEXT[] DEFAULT '{}';
""")

    gen.append("\n-- ============================================================")
    gen.append("-- Migration complete. Verify with:")
    gen.append("--   SELECT table_name FROM information_schema.tables")
    gen.append("--   WHERE table_schema = 'public' ORDER BY table_name;")
    gen.append("-- ============================================================")

    return "\n".join(gen)


def _split_sql_statements(sql: str) -> list[str]:
    """Split SQL by ; respecting dollar-quote $$ ... $$ blocks and string literals."""
    stmts = []
    current = []
    in_dollar = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    while i < len(sql):
        c = sql[i]

        # Line comment --
        if not in_dollar and not in_block_comment and c == '-' and i + 1 < len(sql) and sql[i + 1] == '-':
            in_line_comment = True
            current.append(c)
            i += 1
            continue

        if in_line_comment:
            if c == '\n':
                in_line_comment = False
            current.append(c)
            i += 1
            continue

        # Block comment /* */
        if not in_dollar and c == '/' and i + 1 < len(sql) and sql[i + 1] == '*':
            in_block_comment = True
            current.append(c)
            i += 1
            continue

        if in_block_comment:
            if c == '*' and i + 1 < len(sql) and sql[i + 1] == '/':
                in_block_comment = False
            current.append(c)
            i += 1
            continue

        # Dollar quote start/end (PL/pgSQL $$)
        if c == '$' and i + 1 < len(sql) and sql[i + 1] == '$':
            in_dollar = not in_dollar
            current.append(c)
            i += 1
            continue

        # Semicolon separator (only at top level)
        if c == ';' and not in_dollar and not in_block_comment:
            stmt = ''.join(current).strip()
            if stmt:
                stmts.append(stmt)
            current = []
            i += 1
            continue

        current.append(c)
        i += 1

    # Last statement
    stmt = ''.join(current).strip()
    if stmt:
        stmts.append(stmt)

    return stmts


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
        import psycopg2
        url = os.environ.get("SUPABASE_URL", "")
        if not url:
            print("ERROR: SUPABASE_URL not set")
            sys.exit(1)
        proj = url.split("//")[1].split(".")[0]
        pwd = os.environ.get("SUPABASE_DB_PASSWORD", "")
        if not pwd:
            print("ERROR: SUPABASE_DB_PASSWORD not set (use .env)")
            sys.exit(1)
        try:
            conn = psycopg2.connect(
                host=f"db.{proj}.supabase.co", dbname="postgres",
                user="postgres", password=pwd, port=5432, connect_timeout=10
            )
            cur = conn.cursor()
        except Exception as e:
            print(f"ERROR: Cannot connect to Supabase DB: {e}")
            sys.exit(1)

        # Split SQL respecting $$ blocks
        statements = _split_sql_statements(sql)
        ok, fail = 0, 0
        for stmt in statements:
            stmt = stmt.strip()
            # Skip only pure-comment statements (allow comments + SQL combined)
            if not stmt:
                continue
            lines = stmt.split("\n")
            if all(line.strip().startswith("--") for line in lines if line.strip()):
                continue
            try:
                cur.execute(stmt + ";")
                conn.commit()
                ok += 1
            except Exception as e:
                conn.rollback()
                err = str(e)[:120]
                print(f"  WARN: {err}")
                fail += 1

        cur.close()
        conn.close()
        print(f"\nMigration complete: {ok} OK, {fail} WARN")
        print(f"Expected tables: {total_tables}")
        print("Verify in Supabase Dashboard > Database > Tables")
        return

    # Default: print to stdout
    print(sql)


if __name__ == "__main__":
    main()
