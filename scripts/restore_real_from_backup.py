"""Restore seletivo de dados reais (filtra _test_) a partir de backup JSON.gz.

Cenário: cleanup_old_prices global (rodado por test_cleanup_* no CI) varreu dados
reais de produção. Este script restaura apenas rows SEM marcador _test_ nos campos
store_name / ingredient_id / raw_product, com upsert idempotente por id.

Uso (WSL):
    python scripts/restore_real_from_backup.py backup.json.gz --dry-run
    python scripts/restore_real_from_backup.py backup.json.gz --execute
"""

import argparse
import gzip
import json
import os
import sys
from pathlib import Path

from supabase import create_client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TABLES = ["prices", "price_history", "flyers", "scraping_logs", "scraper_health_log", "review_queue"]


def _is_test(row: dict) -> bool:
    for key in ("store_name", "store_id", "ingredient_id", "raw_product", "name"):
        val = row.get(key)
        if isinstance(val, str) and "_test" in val.lower():
            return True
        if isinstance(val, str) and "test " in val.lower():
            return True
        if isinstance(val, str) and val.lower().startswith("test_"):
            return True
    return False


# Colunas GENERATED (ex.: price_per_kg) não podem ser inseridas — o DB recalcula.
GENERATED_COLUMNS = {
    "prices": {"price_per_kg"},
    "price_history": {"price_per_kg"},
}


def _strip_generated(table: str, row: dict) -> dict:
    for col in GENERATED_COLUMNS.get(table, set()):
        row.pop(col, None)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("backup_file")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY ausentes")

    with gzip.open(args.backup_file, "rt", encoding="utf-8") as f:
        data = json.load(f)
    if "data" in data and isinstance(data.get("data"), dict):
        data = data["data"]

    client = create_client(url, key)
    total_restored = 0
    total_filtered = 0

    for table in TABLES:
        rows = data.get(table, [])
        real = [r for r in rows if not _is_test(r)]
        total_filtered += len(rows) - len(real)
        if args.dry_run:
            print(f"[{table}] backup={len(rows)} reais={len(real)} test_filtrados={len(rows)-len(real)}")
            continue
        if not real:
            print(f"[{table}] 0 reais — skip")
            continue
        inserted = 0
        for i in range(0, len(real), 100):
            chunk = [_strip_generated(table, dict(r)) for r in real[i : i + 100]]
            try:
                resp = client.table(table).upsert(chunk, on_conflict="id").execute()
                inserted += len(resp.data) if resp.data else 0
            except Exception:
                try:
                    resp = client.table(table).insert(chunk).execute()
                    inserted += len(resp.data) if resp.data else 0
                except Exception as e:
                    print(f"  [{table}] chunk {i//100}: ERRO {e}")
        total_restored += inserted
        print(f"[{table}] upsert OK ({inserted}/{len(real)})")

    print(f"\nRESUMO: reais={total_filtered} filtrados(test); restaurados={total_restored if not args.dry_run else 'dry-run'}")


if __name__ == "__main__":
    main()
