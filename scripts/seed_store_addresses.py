#!/usr/bin/env python3
"""Seed endereços do stores.yaml para o DB (tabela stores).

Uso:
  python scripts/seed_store_addresses.py --dry-run
  python scripts/seed_store_addresses.py --execute
"""

import argparse
import sys

import yaml

from services.supabase_client import get_service_client


def load_yaml_addresses():
    """Extrai (store_name, address, city, phone, whatsapp) do YAML."""
    with open("config/stores.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    results = []
    for s in data.get("stores", []):
        name = s.get("name")
        units = s.get("units", [])
        config = s.get("config", {})

        addr = None
        city = s.get("cities", [""])[0] if s.get("cities") else ""
        phone = s.get("phone", "")
        whatsapp = s.get("whatsapp", "")

        if units:
            addr = units[0].get("address")
            # Extrair cidade do endereço se não estiver em cities
            if not city and addr:
                # Ex: "Av. Anna Costa, 340 - Vila Matias, Santos"
                parts = [p.strip() for p in addr.split(",")]
                if len(parts) >= 2:
                    city = parts[-1].strip()  # Última parte após vírgula = cidade
        elif config.get("address"):
            addr = config["address"]
            if not city:
                parts = [p.strip() for p in addr.split(",")]
                if len(parts) >= 2:
                    city = parts[-1].strip()

        if addr:
            results.append({
                "name": name,
                "address": addr,
                "city": city,
                "phone": phone,
                "whatsapp": whatsapp,
            })
    return results


def seed_addresses(dry_run: bool = True):
    client = get_service_client()
    yaml_addrs = load_yaml_addresses()
    print(f"Encontrados {len(yaml_addrs)} lojas com endereço no YAML")

    # Buscar stores existentes no DB
    r = client.rpc("exec_sql_query", {
        "sql": "SELECT id, name, address, city FROM stores"
    }).execute()
    db_stores = {row["name"]: row for row in r.data or []}

    updates = []

    for ya in yaml_addrs:
        name = ya["name"]
        if name in db_stores:
            db = db_stores[name]
            # Só atualiza se DB estiver vazio
            if not db.get("address") and ya["address"]:
                updates.append({
                    "id": db["id"],
                    "address": ya["address"],
                    "city": ya["city"] or db.get("city", ""),
                    "phone": ya["phone"] or db.get("phone", ""),
                })
        else:
            # Store não existe no DB - seria insert (mas stores vêm do YAML sync normal)
            pass

    print(f"  {len(updates)} lojas para atualizar endereço")
    for u in updates:
        print(f"    {u['id']}: {u['address'][:50]} ({u['city']})")

    if not dry_run and updates:
        for u in updates:
            client.table("stores").update({
                "address": u["address"],
                "city": u["city"],
                "phone": u["phone"],
            }).eq("id", u["id"]).execute()
        print("  Atualizado!")

    return len(updates)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_false", dest="dry_run")
    args = parser.parse_args()

    print(f"{'DRY-RUN' if args.dry_run else 'EXECUTE'} seed endereços")
    updated = seed_addresses(args.dry_run)
    print(f"Total: {updated} lojas {'seriam' if args.dry_run else 'foram'} atualizadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())