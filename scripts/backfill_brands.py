#!/usr/bin/env python3
"""Backfill marcas nos preços + normalizar ''→'Desconhecido' + migrar resolved→approved.

Uso:
  python scripts/backfill_brands.py --dry-run
  python scripts/backfill_brands.py --execute
"""

import argparse
import sys
from parsers.brand_extractor import extract_brand
from services.supabase_client import get_service_client


def fetch_ingredients():
    client = get_service_client()
    r = client.rpc("exec_sql_query", {
        "sql": "SELECT canonical_name, brands FROM ingredients WHERE active = true"
    }).execute()
    return {row["canonical_name"]: row["brands"] or [] for row in r.data or []}


def backfill_brands(dry_run: bool = True):
    client = get_service_client()
    ingredients = fetch_ingredients()
    all_ings = [{"canonical_name": k, "brands": v} for k, v in ingredients.items()]

    # 1. Buscar preços com brand 'Desconhecido' OU '' (vazio) - prioriza recentes
    sql = """
        SELECT id, ingredient_id, raw_product, brand
        FROM prices
        WHERE (brand = 'Desconhecido' OR brand = '' OR brand IS NULL)
          AND ingredient_id IS NOT NULL
          AND raw_product IS NOT NULL
        ORDER BY collected_at DESC
        LIMIT 5000
    """
    r = client.rpc("exec_sql_query", {"sql": sql}).execute()
    rows = r.data or []
    print(f"Encontrados {len(rows)} preços para reprocessar")

    if not rows:
        return 0, 0

    updates = []
    for row in rows:
        ing_id = row["ingredient_id"]
        raw = row["raw_product"]
        current = row["brand"] or ""
        ing_brands = ingredients.get(ing_id, [])
        new_brand = extract_brand(raw, {"brands": ing_brands}, all_ingredients=all_ings)
        if new_brand != "Desconhecido" and new_brand != current:
            updates.append({"id": row["id"], "brand": new_brand})

    print(f"  {len(updates)} preços terão marca atualizada")

    if not dry_run and updates:
        # Batch update via table API
        batch_size = 100
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i+batch_size]
            for u in batch:
                client.table("prices").update({"brand": u["brand"]}).eq("id", u["id"]).execute()
            print(f"  Atualizados {min(i+batch_size, len(updates))}/{len(updates)}")

    return len(rows), len(updates)


def migrate_resolved_to_approved(dry_run: bool = True):
    client = get_service_client()
    # Contar resolved
    r = client.rpc("exec_sql_query", {
        "sql": "SELECT COUNT(*) as c FROM review_queue WHERE status = 'resolved'"
    }).execute()
    count = r.data[0]["c"] if r.data else 0
    print(f"Itens 'resolved' no review_queue: {count}")

    if not dry_run and count > 0:
        client.table("review_queue").update({"status": "approved"}).eq("status", "resolved").execute()
        print(f"  Migrados {count} itens: resolved -> approved")

    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_false", dest="dry_run")
    args = parser.parse_args()

    print(f"{'DRY-RUN' if args.dry_run else 'EXECUTE'} backfill de marcas")

    total, updated = backfill_brands(args.dry_run)
    migrated = migrate_resolved_to_approved(args.dry_run)

    if args.dry_run:
        print(f"\nResumo: {total} preços analisados, {updated} seriam atualizados, {migrated} resolved migrados")
    else:
        print(f"\nResumo: {total} preços analisados, {updated} atualizados, {migrated} resolved migrados")
    return 0


if __name__ == "__main__":
    sys.exit(main())