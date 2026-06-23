#!/usr/bin/env python3
"""
Valida que o banco Supabase tem TODAS as tabelas, colunas, constraints,
Ã­ndices e funÃ§Ãµes esperadas pelas migrations PHASE 1-13.

Uso:
    python scripts/validate_db_schema.py
"""
import os
import sys
import psycopg2

EXPECTED_TABLES = [
    "prices", "price_history", "review_queue", "scraping_logs",
    "stores", "flyers", "ingredients", "schedules",
    "scrape_frequencies", "alert_recipients", "alert_rules", "feature_flags",
]

EXPECTED_COLUMNS = {
    "prices": [
        "id", "ingredient_id", "store_id", "source", "store_name",
        "raw_product", "raw_price", "raw_unit", "collected_at",
        "valid_from", "valid_until", "validity_raw", "collected_weekday",
        "is_promotion", "tier", "confidence", "normalized", "city",
        "logistics", "brand",
    ],
    "review_queue": [
        "id", "raw_product", "raw_price", "raw_unit", "store_name",
        "source", "confidence", "suggestions", "validity_raw", "status",
        "resolved_ingredient", "collected_at", "reviewed_at", "brand",
        "image_url", "source_url", "match_reason", "match_type", "top3",
    ],
    "ingredients": [
        "id", "canonical_name", "category", "aliases", "unit_target",
        "active", "created_at", "updated_at", "brands", "search_terms",
    ],
}

EXPECTED_CONSTRAINTS = {
    "prices": ["prices_ingredient_id_store_id_collected_at_key"],
    "price_history": ["price_history_ingredient_id_store_id_collected_at_key"],
}

EXPECTED_INDEXES = [
    "idx_prices_ing_collected",
    "idx_history_ing_collected",
    "idx_review_collected",
    "idx_stores_name",
    "idx_logs_store_started",
]

EXPECTED_FUNCTIONS = ["upsert_price_rpc", "cleanup_old_prices", "cleanup_old_logs", "cleanup_old_flyers"]


def get_connection():
    url = os.environ.get("SUPABASE_URL", "")
    pwd = os.environ.get("SUPABASE_DB_PASSWORD", "")
    if not url or not pwd:
        print("ERROR: SUPABASE_URL and SUPABASE_DB_PASSWORD must be set")
        sys.exit(1)
    proj = url.split("//")[1].split(".")[0]
    return psycopg2.connect(
        host=f"db.{proj}.supabase.co", dbname="postgres",
        user="postgres", password=pwd, port=5432, connect_timeout=10,
    )


def validate_tables(cur):
    print("=== TABLES ===")
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")
    db_tables = {r[0] for r in cur.fetchall()}
    ok = 0
    for t in EXPECTED_TABLES:
        if t in db_tables:
            print(f"  [OK] {t}")
            ok += 1
        else:
            print(f"  [!!] {t} MISSING")
    extra = db_tables - set(EXPECTED_TABLES)
    if extra:
        print(f"  [--] Extras: {', '.join(sorted(extra))}")
    return ok, len(EXPECTED_TABLES)


def validate_columns(cur):
    print("\n=== COLUMNS ===")
    ok, total = 0, 0
    for table, expected in EXPECTED_COLUMNS.items():
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position;",
            (table,),
        )
        db_cols = {r[0] for r in cur.fetchall()}
        for col in expected:
            total += 1
            if col in db_cols:
                ok += 1
            else:
                print(f"  âŒ {table}.{col} MISSING")
    print(f"  {ok}/{total} columns OK")
    return ok, total


def validate_constraints(cur):
    print("\n=== CONSTRAINTS ===")
    ok, total = 0, 0
    for table, names in EXPECTED_CONSTRAINTS.items():
        for cname in names:
            total += 1
            cur.execute(
                "SELECT 1 FROM pg_constraint WHERE conrelid = %s::regclass AND conname = %s;",
                (table, cname),
            )
            if cur.fetchone():
                print(f"  âœ… {table}: {cname}")
                ok += 1
            else:
                print(f"  âŒ {table}: {cname} MISSING")
    return ok, total


def validate_indexes(cur):
    print("\n=== INDEXES ===")
    ok = 0
    for idx in EXPECTED_INDEXES:
        cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s;", (idx,))
        if cur.fetchone():
            print(f"  âœ… {idx}")
            ok += 1
        else:
            print(f"  âŒ {idx} MISSING")
    return ok, len(EXPECTED_INDEXES)


def validate_functions(cur):
    print("\n=== FUNCTIONS ===")
    ok = 0
    for fn in EXPECTED_FUNCTIONS:
        cur.execute("SELECT 1 FROM pg_proc WHERE proname = %s;", (fn,))
        if cur.fetchone():
            print(f"  âœ… {fn}()")
            ok += 1
        else:
            print(f"  âŒ {fn}() MISSING")
    return ok, len(EXPECTED_FUNCTIONS)


def main():
    conn = get_connection()
    cur = conn.cursor()

    results = []
    results.append(validate_tables(cur))
    results.append(validate_columns(cur))
    results.append(validate_constraints(cur))
    results.append(validate_indexes(cur))
    results.append(validate_functions(cur))

    cur.close()
    conn.close()

    total_ok = sum(o for o, _ in results)
    total_exp = sum(t for _, t in results)

    print(f"\n{'='*40}")
    print(f"RESULT: {total_ok}/{total_exp} checks passed")
    if total_ok == total_exp:
        print("ALL PHASES VERIFIED âœ…")
    else:
        print("SOME PHASES MISSING âŒ")
        sys.exit(1)


if __name__ == "__main__":
    main()

