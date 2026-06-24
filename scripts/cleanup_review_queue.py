#!/usr/bin/env python3
"""Cleanup review_queue: remove test data and reject out-of-scope items."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_dotenv = Path(__file__).parent.parent / ".env"
if _dotenv.exists():
    with open(_dotenv, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                v = v.strip("\"'")
                os.environ.setdefault(k.strip(), v)

from services.supabase_client import get_service_client

client = get_service_client()

print("=" * 60)
print("CustoDoce — Cleanup Review Queue")
print("=" * 60)

# 1. Delete test data
print("\n1. Deletando dados de teste...")
r = client.table("review_queue").delete().in_(
    "store_name", ["Test Review Queue Store", "E2E Test Store", "Test Store"]
).execute()
print(f"   Deletados: {len(r.data or [])} itens de teste")

# 2. Reject out-of-scope from Pao de Acucar Fresh
CONFECTIONERY_TERMS = [
    "chocolate", "açúcar", "acucar", "farinha", "manteiga",
    "creme de leite", "leite condensado", "fermento", "baunilha",
    "coco", "granulado", "cobertura", "essencia", "leite em pó",
    "leite ninho", "margarina", "glucose", "glicose", "cacau",
]

print("\n2. Carregando pendentes do Pao de Acucar Fresh...")
pao_items = client.table("review_queue").select("id,raw_product").eq("store_name", "Pao de Acucar Fresh").eq("status", "pending").execute()
pao_to_reject = []
for item in (pao_items.data or []):
    prod = item["raw_product"].lower()
    if not any(t in prod for t in CONFECTIONERY_TERMS):
        pao_to_reject.append(item["id"])
print(f"   {len(pao_items.data or [])} pendentes, {len(pao_to_reject)} fora do escopo")

if pao_to_reject:
    r = client.table("review_queue").update({"status": "rejected"}).in_("id", pao_to_reject).execute()
    print(f"   Rejeitados: {len(r.data or [])} itens do Pao de Acucar Fresh")

# 3. Reject out-of-scope from Extra Folheteria
print("\n3. Carregando pendentes do Extra Folheteria...")
extra_items = client.table("review_queue").select("id,raw_product").eq("store_name", "Extra Folheteria").eq("status", "pending").execute()
extra_to_reject = []
for item in (extra_items.data or []):
    prod = item["raw_product"].lower()
    if not any(t in prod for t in CONFECTIONERY_TERMS):
        extra_to_reject.append(item["id"])
print(f"   {len(extra_items.data or [])} pendentes, {len(extra_to_reject)} fora do escopo")

if extra_to_reject:
    r = client.table("review_queue").update({"status": "rejected"}).in_("id", extra_to_reject).execute()
    print(f"   Rejeitados: {len(r.data or [])} itens do Extra Folheteria")

# 4. Reject Dona Dani non-ingredient products
DONA_DANI_JUNK = [
    "bolo cremoso", "recheio pronto", "cobertura glacê", "cake chocolate",
    "procreme", "pão de ló", "pao de lo", "chococookies",
    "geléia brilho", "brilho chocolate", "ovo pó",
]
print("\n4. Carregando pendentes da Dona Dani Ingredientes...")
dani_items = client.table("review_queue").select("id,raw_product").eq("store_name", "Dona Dani Ingredientes").eq("status", "pending").execute()
dani_to_reject = []
for item in (dani_items.data or []):
    prod = item["raw_product"].lower()
    if any(t in prod for t in DONA_DANI_JUNK):
        dani_to_reject.append(item["id"])
print(f"   {len(dani_items.data or [])} pendentes, {len(dani_to_reject)} fora do escopo")

if dani_to_reject:
    r = client.table("review_queue").update({"status": "rejected"}).in_("id", dani_to_reject).execute()
    print(f"   Rejeitados: {len(r.data or [])} itens da Dona Dani")

# 5. Final count
print("\n5. Contagem final de pendentes por loja:")
remaining = client.table("review_queue").select("store_name,status").eq("status", "pending").execute()
from collections import Counter
counts = Counter(item["store_name"] for item in (remaining.data or []))
for store, count in sorted(counts.items(), key=lambda x: -x[1]):
    print(f"   {store:40s} {count} pendentes")
print(f"\n   TOTAL PENDENTES: {len(remaining.data or [])}")
print("\n✅ Limpeza concluída!")
