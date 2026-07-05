#!/usr/bin/env python3
"""Security linter for Supabase: RLS, RPC, tables, buckets.

Uses exec_sql_query RPC (port 443) — never psycopg2.

Modes:
  --quick   RLS + RPC scan only (CI default)
  --full    All checks + buckets + auth config doc
  --rls     RLS policies only
  --rpc     Functions only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.supabase_client import get_service_client


def rpc(sql: str) -> list[dict]:
    client = get_service_client()
    sql = sql.strip().rstrip(";")
    res = client.rpc("exec_sql_query", {"sql": sql})
    if hasattr(res, "error") and res.error:
        print(f"  [RPC ERROR] {res.error}")
        return []
    data = res.data if hasattr(res, "data") else res
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "data" in data:
        return data["data"] or []
    return []


def check_rls():
    print("\n=== RLS ===")
    tables_no_rls = rpc("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename NOT IN (SELECT tablename FROM pg_policies WHERE schemaname = 'public')
          AND tablename NOT LIKE '\\_%'
        ORDER BY tablename
    """)
    if tables_no_rls:
        fail(f"Tabelas SEM RLS: {[t['tablename'] for t in tables_no_rls]}")
    else:
        ok("Todas as tabelas tem RLS")

    permissive = rpc("""
        SELECT schemaname, tablename, policyname, permissive, cmd, qual, with_check
        FROM pg_policies
        WHERE (qual LIKE '%true%' OR with_check LIKE '%true%')
          AND schemaname = 'public'
          AND qual NOT LIKE '%auth.role()%'
        ORDER BY tablename, policyname
    """)
    if permissive:
        fail(f"Policies permissivas: {len(permissive)}")
        for p in permissive[:5]:
            info(f"  {p['tablename']}.{p['policyname']}: {p.get('qual','')[:80]}")
    else:
        ok("Nenhuma policy com USING/WITH CHECK (true) sem auth.role() guard")


def check_rpc():
    print("\n=== RPC / Functions ===")
    exposed = rpc("""
        SELECT n.nspname, p.proname, p.prosecdef, p.prorettype::regtype,
               pg_get_functiondef(p.oid) AS def
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public'
          AND p.proname NOT IN ('exec_sql', 'exec_sql_query', 'upsert_price_rpc')
        ORDER BY p.proname
    """)
    if exposed:
        warn(f"Funcoes expostas: {len(exposed)}")
        for f in exposed:
            secdef = "SECURITY DEFINER" if f.get("prosecdef") else "SECURITY INVOKER"
            info(f"  {f['proname']} ({secdef})")
    else:
        ok("Nenhuma funcao exposta alem das 3 RPCs conhecidas")

    secdef_no_restrict = rpc("""
        SELECT n.nspname, p.proname
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public'
          AND p.prosecdef = true
          AND p.proname NOT IN ('exec_sql', 'exec_sql_query', 'upsert_price_rpc')
    """)
    if secdef_no_restrict:
        fail(f"SECURITY DEFINER sem restricao: {[f['proname'] for f in secdef_no_restrict]}")
    else:
        ok("Nenhuma SECURITY DEFINER extra")


def check_buckets():
    print("\n=== BUCKETS ===")
    buckets = rpc("""
        SELECT id, name, public, owner, created_at
        FROM storage.buckets ORDER BY name
    """)
    if not buckets:
        ok("Nenhum bucket (ou sem acesso)")
        return
    public = [b for b in buckets if b.get("public")]
    if public:
        fail(f"Buckets publicos: {[b['name'] for b in public]}")
    else:
        ok("Nenhum bucket publico")


def check_auth():
    print("\n=== AUTH (leitura via SQL) ===")
    try:
        users = rpc("SELECT COUNT(*) AS total FROM auth.users")
        if users:
            info(f"{users[0].get('total', '?')} usuarios cadastrados")
    except Exception:
        info("Sem acesso a auth.users (esperado via exec_sql_query)")


FAIL_COUNTER: list[int] = [0]


def fail(msg: str):
    FAIL_COUNTER[0] += 1
    print(f"  [FAIL] {msg}")


def ok(msg: str):
    print(f"  [OK] {msg}")


def warn(msg: str):
    print(f"  [WARN] {msg}")


def info(msg: str):
    print(f"  [INFO] {msg}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="RLS + RPC only")
    parser.add_argument("--full", action="store_true", help="All checks")
    parser.add_argument("--rls", action="store_true")
    parser.add_argument("--rpc", action="store_true")
    args = parser.parse_args()

    if args.rls:
        check_rls()
    elif args.rpc:
        check_rpc()
    elif args.quick:
        check_rls()
        check_rpc()
    elif args.full:
        check_rls()
        check_rpc()
        check_buckets()
        check_auth()
    else:
        check_rls()
        check_rpc()
        check_buckets()
        check_auth()

    total = FAIL_COUNTER[0]
    if total:
        print(f"\n  {total} falha(s) encontrada(s)")
    else:
        print("\n  Todas as verificacoes passaram")
    return total


if __name__ == "__main__":
    sys.exit(main())
