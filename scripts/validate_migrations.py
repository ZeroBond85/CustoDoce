#!/usr/bin/env python3
"""Valida o ledger de migrations: compara migrations locais com o que foi
aplicado no banco (tabela public.schema_migrations).

Modos:
  --check (default) : compara disco vs banco, reporta drift/ordem/faltantes.
  --bootstrap       : registra retroativamente migrations ja aplicadas no banco
                      que nao estao no ledger (migrations 001..017).

Sempre usa REST API (RPC exec_sql_query / exec_sql, porta 443) para ser
compatível com CI/CD. NUNCA psycopg2 (AGENTS.md regra #4).
"""

import argparse
import hashlib
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"


def get_client():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)
    return create_client(url, key)


def run_query(client, sql):
    """Executa SQL via RPC (exec_sql aceita DDL; exec_sql_query para SELECT)."""
    try:
        res = client.rpc("exec_sql_query", {"sql": sql}).execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"  Query Failed: {sql}\n  Error: {e}")
        return None


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def list_local_migrations() -> list[dict]:
    """Lista migrations locais (supabase/migrations/NNN_*.sql), ordenadas."""
    if not MIGRATIONS_DIR.exists():
        print(f"ERROR: {MIGRATIONS_DIR} não existe")
        sys.exit(1)
    out = []
    for p in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = p.stem.split("_", 1)[0]
        out.append(
            {
                "version": version,
                "name": p.name,
                "path": p,
                "checksum": sha256_of(p),
            }
        )
    return out


def fetch_db_ledger(client) -> dict[str, dict]:
    rows = run_query(client, "SELECT version, name, checksum FROM public.schema_migrations")
    if rows is None:
        return {}
    return {r["version"]: r for r in rows}


def table_exists(client) -> bool:
    rows = run_query(
        client,
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'schema_migrations'",
    )
    return bool(rows)


def validate_migrations(client) -> int:
    local = list_local_migrations()
    db = fetch_db_ledger(client)

    print(f"=== MIGRATION LEDGER ({len(local)} locais / {len(db)} no banco) ===")

    errors: list[str] = []
    missing = [m for m in local if m["version"] not in db]
    if missing:
        errors.append(f"  [!!] {len(missing)} migrations locais NAO registradas no ledger")
        for m in missing:
            print(f"       - {m['name']} (não registrada)")

    # Ordem: versões devem ser crescentes no disco (gaps são normais — nem toda
    # migração numerada existe em supabase/migrations/; algumas históricas estão
    # em supabase/ raiz). Só quebra se a ordem não for estritamente crescente.
    versions = sorted(local, key=lambda m: m["version"])
    prev: str | None = None
    for m in versions:
        v = m["version"]
        if prev is not None and int(v) <= int(prev):
            errors.append(f"  [!!] Ordem inválida: {prev} depois de {v}")
        prev = v

    # Checksum drift: migration registrada mas com conteúdo diferente do disco.
    for m in local:
        row = db.get(m["version"])
        if not row:
            continue
        if row.get("checksum") != m["checksum"]:
            db_checksum = (row.get("checksum") or "?")[:12]
            errors.append(
                f"  [!!] {m['name']} DRIFT: checksum no banco {db_checksum} "
                f"!= local {m['checksum'][:12]} (migration editada após aplicar?)"
            )

    if not errors:
        print("  [OK] Ledger consistente: ordem OK, checksums OK, sem drift.")
        return 0

    print("\n".join(errors))
    print("\n[FAIL] Divergências no ledger de migrations.")
    print("Dica: se uma migration foi editada após aplicar, rode:")
    print("  python scripts/validate_migrations.py --bootstrap")
    return 1


def bootstrap(client) -> int:
    """Registra no ledger todas as migrations locais ainda não presentes."""
    if not table_exists(client):
        print("ERROR: tabela schema_migrations não existe no banco.")
        print("Aplique supabase/consolidated_migration.sql (PHASE 0) antes.")
        return 1

    local = list_local_migrations()
    db = fetch_db_ledger(client)
    added = 0
    for m in local:
        if m["version"] in db:
            continue
        try:
            client.table("schema_migrations").upsert(
                {"version": m["version"], "name": m["name"], "checksum": m["checksum"]},
                on_conflict="version",
            ).execute()
            print(f"  [OK] registrado {m['name']}")
            added += 1
        except Exception as e:
            print(f"  [!!] falha ao registrar {m['name']}: {e}")
    print(f"\nBootstrap: {added} migrations registradas.")
    return 0 if added or not db else 1


def main():
    parser = argparse.ArgumentParser(description="Valida ledger de migrations")
    parser.add_argument("--bootstrap", action="store_true", help="Registra migrations aplicadas retroativamente")
    args = parser.parse_args()

    client = get_client()
    if args.bootstrap:
        return bootstrap(client)
    return validate_migrations(client)


if __name__ == "__main__":
    sys.exit(main())
