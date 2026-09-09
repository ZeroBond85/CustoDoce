"""Sincroniza campos do YAML (exclude_terms, search_terms, brands) para a tabela
`ingredients` do Supabase, SEM sobrescrever aliases (gerenciados no dashboard).

Motivo: o matcher em runtime lê `ingredients` do DB, mas os guard rails
(exclude_terms) são definidos no YAML. Sem sync, FPs continuam entrando.

Uso:
    python scripts/sync_ingredient_fields.py --dry-run
    python scripts/sync_ingredient_fields.py --execute
"""

import argparse
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from services.supabase_client import get_service_client

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# exclude_terms = fonte YAML (guard rails críticos). search_terms/brands = merge
# (YAML ∪ DB) para preservar enriquecimento manual do dashboard.
# match_threshold = YAML → DB (exact, YAML wins)
_SYNC_EXACT = ["exclude_terms", "match_threshold"]
_SYNC_MERGE = ["search_terms", "brands"]


def load_yaml_ingredients() -> list[dict]:
    with open(os.path.join(_REPO_ROOT, "config", "ingredients.yaml"), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("ingredients", [])


def _clean_alias(alias: str) -> str | None:
    """Remove artifacts de teste (Test Approve UUID/Name/Fuzzy, Duplicate Price)."""
    low = alias.lower()
    if low.startswith("test approve") or low.startswith("duplicate price"):
        return None
    return alias


def _is_list(value) -> bool:
    return isinstance(value, list | tuple | set)


def _fields_differ(field: str, yaml_value, db_value) -> bool:
    """Comparação versátil: listas por set, escalares por valor (numérico normalizado)."""
    yv = yaml_value if yaml_value is not None else ([] if field in _SYNC_EXACT else None)
    dv = db_value if db_value is not None else ([] if field in _SYNC_EXACT else None)
    if _is_list(yv) or _is_list(dv):
        return set(yv or []) != set(dv or [])
    try:
        return float(yv) != float(dv)
    except (TypeError, ValueError):
        return yv != dv


def _field_repr(field: str, value):
    """len() para listas, valor puro para escalares (feedback de diff)."""
    if value is None:
        return 0 if field in _SYNC_EXACT else None
    if _is_list(value):
        return len(value)
    return value


def main():
    parser = argparse.ArgumentParser(description="Sync exclude_terms/search_terms/brands YAML -> DB")
    parser.add_argument("--dry-run", action="store_true", help="Só mostra diffs")
    parser.add_argument("--execute", action="store_true", help="Aplica updates")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        parser.error("Use --dry-run ou --execute")

    client = get_service_client()
    yaml_ings = load_yaml_ingredients()

    res = client.rpc(
        "exec_sql_query",
        {"sql": "SELECT canonical_name, exclude_terms, search_terms, brands, aliases, match_threshold FROM ingredients"},
    ).execute()
    db_by_name = {}
    for r in res.data or []:
        db_by_name[r["canonical_name"]] = r

    pending = []
    for y in yaml_ings:
        name = y["canonical"]
        db = db_by_name.get(name)
        if not db:
            pending.append((name, "FALTA_NO_DB", y))
            continue
        for field in _SYNC_EXACT:
            yv = y.get(field, [])
            dv = db.get(field) or []
            if _fields_differ(field, yv, dv):
                pending.append((name, field, y))
        for field in _SYNC_MERGE:
            yv = set(y.get(field, []))
            dv = set(db.get(field) or [])
            if not yv.issubset(dv):
                pending.append((name, field, y))

    print(f"Campos defasados encontrados: {len(pending)}")
    for name, field, y in pending:
        if field == "FALTA_NO_DB":
            print(f"  [FALTA] {name}")
        else:
            print(
                f"  [{field}] {name}: YAML={_field_repr(field, y.get(field, []))} DB={_field_repr(field, db_by_name.get(name, {}).get(field))}"
            )

    alias_cleanup = []
    for name, db in db_by_name.items():
        aliases = db.get("aliases") or []
        cleaned = [a for a in aliases if _clean_alias(a)]
        if len(cleaned) != len(aliases):
            alias_cleanup.append((name, aliases, cleaned))
    print(f"\nIngredientes com artifacts de teste nos aliases: {len(alias_cleanup)}")
    for name, before, after in alias_cleanup:
        print(f"  [{name}] {len(before)} -> {len(after)} aliases")

    if args.dry_run:
        print("\n[Dry-run] Nada foi alterado.")
        return

    now = datetime.now(UTC).isoformat()
    errors = 0
    for name, field, y in pending:
        if field == "FALTA_NO_DB":
            print(f"  [SKIP] {name} não está no DB — use seed para criar")
            continue
        if field in _SYNC_EXACT:
            value = y.get(field, [])
        else:
            db = db_by_name.get(name, {})
            value = sorted(set(y.get(field, [])) | set(db.get(field) or []))
        try:
            client.table("ingredients").update({field: value, "updated_at": now}).eq("canonical_name", name).execute()
            print(f"  [OK] {name}.{field} -> {_field_repr(field, value)}")
        except Exception as e:
            print(f"  [ERRO] {name}.{field}: {type(e).__name__}: {e}")
            errors += 1

    for name, before, after in alias_cleanup:
        try:
            client.table("ingredients").update({"aliases": after, "updated_at": now}).eq(
                "canonical_name", name
            ).execute()
            print(f"  [OK] {name}.aliases limpos ({len(before)} -> {len(after)})")
        except Exception as e:
            print(f"  [ERRO] {name}.aliases: {type(e).__name__}: {e}")
            errors += 1

    print(f"\n{'[OK] Sync completo sem erros.' if errors == 0 else f'[ATENÇÃO] {errors} erros.'}")


if __name__ == "__main__":
    main()
