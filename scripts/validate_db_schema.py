#!/usr/bin/env python3
# ruff: noqa: S608  # SQL construído com valores do manifest local (safe)
"""Valida que o banco Supabase tem TODAS as tabelas, colunas, constraints, índices e
funções esperadas pelas migrations.

Sempre usa REST API (RPC exec_sql_query, porta 443) para ser compatível com CI/CD.
Fonte de verdade: config/schema_manifest.json (gerado por generate_schema_manifest.py)
+ listas adicionais de índices/funções aqui.

Saída: exit 0 se TODAS as checagens passarem, exit 1 caso contrário.
NUNCA é no-op: se a query de tabelas voltar vazia, o script falha.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "config" / "schema_manifest.json"

# Índices de performance esperados (não capturados pelo manifest).
EXPECTED_INDEXES = [
    "idx_prices_ing_collected",
    "idx_history_ing_collected",
    "idx_review_collected",
    "idx_stores_name",
    "idx_logs_store_started",
    "idx_recipe_items_recipe",
    "idx_prices_price_per_kg",  # generated column index
    "idx_prices_promo_collected",  # partial index
    "idx_prices_store_collected",  # FK index
    "idx_review_status_collected",  # review queue filter
    "idx_flyers_store_ocr_collected",  # flyer filter
    "idx_ingredients_active_name",  # active filter
]

# Funções RPC esperadas.
EXPECTED_FUNCTIONS = [
    "upsert_price_rpc",
    "cleanup_old_prices",
    "cleanup_old_logs",
    "cleanup_old_flyers",
]


def load_manifest() -> dict:
    """Carrega o schema manifest (fonte de verdade) — falha se ausente/corrompido."""
    if not MANIFEST_PATH.exists():
        print(f"ERROR: manifest não encontrado: {MANIFEST_PATH}")
        sys.exit(1)
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    tables = {k: v for k, v in manifest.items() if k != "_meta"}
    if not tables:
        print("ERROR: manifest vazio — nenhuma tabela esperada")
        sys.exit(1)
    return tables


def get_client():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)
    return create_client(url, key)


def run_query(client, sql):
    """Executa SQL via exec_sql_query RPC (porta 443). Retorna lista de dicts."""
    try:
        res = client.rpc("exec_sql_query", {"sql": sql}).execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"  Query Failed: {sql}\n  Error: {e}")
        return None


def _safe_set(client, sql):
    """Executa query e devolve set de valores da primeira coluna (ou None se falhou)."""
    rows = run_query(client, sql)
    if rows is None:
        return None
    return {list(r.values())[0] for r in rows}


def validate_tables(client, expected_tables):
    print("=== TABLES ===")
    sql = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' ORDER BY table_name"
    )
    db_tables = _safe_set(client, sql)
    # Materialized views NÃO aparecem em information_schema.tables — estão em
    # pg_matviews. O manifest inclui v_latest_prices como tabela.
    matview_sql = "SELECT matviewname FROM pg_matviews"
    matviews = _safe_set(client, matview_sql)
    if db_tables is not None and matviews is not None:
        db_tables |= matviews
    if db_tables is None:
        return 0, len(expected_tables)
    ok = 0
    for t in sorted(expected_tables):
        if t in db_tables:
            print(f"  [OK] {t}")
            ok += 1
        else:
            print(f"  [!!] {t} MISSING")
    return ok, len(expected_tables)


def validate_columns(client, expected_columns):
    print("\n=== COLUMNS ===")
    ok, total = 0, 0
    for table, spec in sorted(expected_columns.items()):
        cols = spec.get("columns", [])
        # pg_attribute funciona para tabelas E materialized views
        # (information_schema.columns não expõe colunas de matviews).
        sql = (
            "SELECT a.attname FROM pg_attribute a "
            "JOIN pg_class r ON r.oid = a.attrelid "
            f"WHERE r.relname = '{table}' AND a.attnum > 0 AND NOT a.attisdropped"  # noqa: S608
        )
        db_cols = _safe_set(client, sql)
        if db_cols is None:
            total += len(cols)
            continue
        for col in cols:
            total += 1
            if col in db_cols:
                ok += 1
            else:
                print(f"  [-] {table}.{col} MISSING")
    print(f"  {ok}/{total} columns OK")
    return ok, total


def validate_constraints(client, expected_tables):
    print("\n=== CONSTRAINTS (PK + UNIQUE) ===")
    ok, total = 0, 0
    for table, spec in sorted(expected_tables.items()):
        pk = spec.get("constraints", {}).get("pk", [])
        uniques = spec.get("constraints", {}).get("unique", [])
        for col in pk:
            total += 1
            sql = (
                "SELECT 1 FROM pg_constraint WHERE conrelid = "
                f"'{table}'::regclass AND contype = 'p'"  # noqa: S608
            )
            if run_query(client, sql):
                print(f"  [OK] {table}: PK ({', '.join(col) if isinstance(col, list) else col})")
                ok += 1
            else:
                print(f"  [-] {table}: PK MISSING")
        for cols in uniques:
            total += 1
            col_list = ", ".join(cols)
            sql = (
                "SELECT 1 FROM pg_index i JOIN pg_constraint c ON c.conindid = i.indexrelid "
                f"WHERE c.conrelid = '{table}'::regclass AND c.contype = 'u' "  # noqa: S608
                "AND array_to_string(i.indkey, ',') IS NOT NULL"
            )
            if run_query(client, sql):
                print(f"  [OK] {table}: UNIQUE ({col_list})")
                ok += 1
            else:
                print(f"  [-] {table}: UNIQUE ({col_list}) MISSING")
    return ok, total


def validate_indexes(client):
    print("\n=== INDEXES ===")
    ok = 0
    for idx in EXPECTED_INDEXES:
        sql = f"SELECT 1 FROM pg_indexes WHERE indexname = '{idx}'"  # noqa: S608
        if run_query(client, sql):
            print(f"  [OK] {idx}")
            ok += 1
        else:
            print(f"  [-] {idx} MISSING")
    return ok, len(EXPECTED_INDEXES)


def validate_functions(client):
    print("\n=== FUNCTIONS ===")
    ok = 0
    for fn in EXPECTED_FUNCTIONS:
        sql = f"SELECT 1 FROM pg_proc WHERE proname = '{fn}'"  # noqa: S608
        if run_query(client, sql):
            print(f"  [OK] {fn}()")
            ok += 1
        else:
            print(f"  [-] {fn}() MISSING")
    return ok, len(EXPECTED_FUNCTIONS)


def main():
    expected_tables = load_manifest()
    client = get_client()

    # Anti no-op: se a query de tabelas falhar ou voltar vazia, abortar.
    probe = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public'"
    )
    db_tables = _safe_set(client, probe)
    if db_tables is None:
        print("\n[FATAL] Falha ao consultar tabelas via exec_sql_query RPC.")
        sys.exit(1)
    if not db_tables:
        print("\n[FATAL] Nenhuma tabela encontrada no schema 'public' — algo errado.")
        sys.exit(1)

    results = [
        validate_tables(client, expected_tables),
        validate_columns(client, expected_tables),
        validate_constraints(client, expected_tables),
        validate_indexes(client),
        validate_functions(client),
    ]

    total_ok = sum(o for o, _ in results)
    total_exp = sum(t for _, t in results)
    print(f"\n{'=' * 40}")
    print(f"RESULT: {total_ok}/{total_exp} checks passed")
    if total_ok == total_exp:
        print("ALL PHASES VERIFIED [OK]")
        return 0
    print("SOME PHASES MISSING [FAIL]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
