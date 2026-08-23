#!/usr/bin/env python3
"""FASE 7 — Recuperação da review_queue: re-match com matcher novo + combined >= 0.80.

Replica EXATAMENTE a lógica de services/collector.py::process_price_match
(linhas ~236-256): match_ingredient -> se score>=60 e AI habilitado, soma
semantic_score via sm.combined_score. Itens com combined>=0.80 viram preço.

Modos:
  --dry-run   (default)  apenas lista candidatos a recuperação
  --execute   insere os preços e marca review_queue como resolved
  --delete-legacy         remove itens pending legados (fora de escopo / teste)
  --reject-stores         rejeita lojas fora do escopo regional
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.collector import build_product_entry
from services.config_db import get_active_ingredients
from services.price_repository import batch_upsert_prices
from services.supabase_client import get_service_client
from parsers.matcher import match_ingredient

client = get_service_client()
REVIEW_THRESHOLD = 0.80


def load_pending(client: object | None = None) -> list[dict]:
    """Carrega todos os itens pending da review_queue (com retry)."""
    c = client or globals()["client"]
    rows: list[dict] = []
    page = 0
    while True:
        r = (
            c.table("review_queue")
            .select("*")
            .eq("status", "pending")
            .range(page * 500, page * 500 + 499)
            .execute()
        )
        data = r.data or []
        if not data:
            break
        rows.extend(data)
        if len(data) < 500:
            break
        page += 1
    return rows


def archive_below_threshold(client: object | None = None, threshold: float = 0.70) -> int:
    """T1.3 — Arquiva (status='rejected') pendentes com confidence < threshold.

    Lote reversível (só flip de status) para limpar o backlog legado que nunca
    seria recuperado. Itens no gray-zone (>= threshold) são preservados.
    """
    c = client or globals()["client"]
    r = (
        c.table("review_queue")
        .update({"status": "rejected"})
        .eq("status", "pending")
        .lt("confidence", threshold)
        .execute()
    )
    return len(r.data or [])


def reject_false_positives(
    client: object | None = None,
    ingredients: list[dict] | None = None,
    threshold: float = 60.0,
) -> int:
    """T1.4 — Rejeita pendentes que NÃO casam com nenhum ingrediente ativo.

    Itens cujo re-match com o matcher novo (com excludes do T1.5) não encontra
    candidato eram falsos-positivos do matcher antigo — rejeitar em lote.
    """
    c = client or globals()["client"]
    ingredients = ingredients or get_active_ingredients()
    pending = load_pending(c)
    rejected = 0
    for item in pending:
        product = item.get("raw_product") or ""
        if not product:
            continue
        ing, score, _ = match_ingredient(product, ingredients, threshold=threshold)
        if not ing or score < threshold:
            c.table("review_queue").update({"status": "rejected"}).eq("id", item["id"]).execute()
            rejected += 1
    return rejected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--delete-legacy", action="store_true")
    parser.add_argument("--reject-stores", action="store_true")
    parser.add_argument(
        "--archive-below",
        type=float,
        default=None,
        help="T1.3: arquiva (rejected) pendentes com confidence abaixo deste valor",
    )
    parser.add_argument(
        "--reject-false-positives",
        action="store_true",
        help="T1.4: rejeita pendentes que não casam com nenhum ingrediente ativo",
    )
    args = parser.parse_args()

    ingredients = get_active_ingredients()
    if not ingredients:
        print("ERRO: nenhum ingrediente carregado")
        sys.exit(1)

    pending = load_pending()
    print(f"Pendentes na review_queue: {len(pending)}")

    # ---- Passo 1: recuperação por re-match ----
    recover = []
    for item in pending:
        product = item.get("raw_product") or ""
        if not product:
            continue
        ing, score, mtype = match_ingredient(product, ingredients, threshold=60.0)
        if not ing or score < 60.0:
            continue
        combined = score / 100.0
        from parsers.semantic_matcher import get_matcher

        sm = get_matcher()
        semantic = sm.get_similarity(product, ing)
        combined = sm.combined_score(score, semantic)
        if combined >= REVIEW_THRESHOLD:
            recover.append(
                {
                    "id": item["id"],
                    "store": item.get("store_name"),
                    "product": product,
                    "ingredient": ing["canonical_name"],
                    "score": score,
                    "semantic": round(semantic, 3),
                    "combined": round(combined, 3),
                    "mtype": mtype,
                    "raw_price": item.get("raw_price"),
                    "raw_unit": item.get("raw_unit"),
                    "brand": item.get("brand"),
                }
            )

    print(f"\n=== RECUPERAÇÃO (combined >= {REVIEW_THRESHOLD}) ===")
    print(f"Candidatos: {len(recover)}")
    for c in sorted(recover, key=lambda x: -x["combined"]):
        print(
            f"  {c['combined']:.3f} | {c['store']:<20} | {c['product'][:50]:<50} "
            f"| {c['ingredient']} | {c['brand']} | raw={c['raw_price']} {c['raw_unit']}"
        )

    if args.execute and recover:
        entries = []
        for c in recover:
            entry = build_product_entry(
                {"name": c["store"]},
                {"canonical_name": c["ingredient"]},
                c["product"],
                c["raw_price"],
                c["raw_unit"],
                c["combined"],
                brand=c["brand"],
            )
            entries.append(entry)
        result = batch_upsert_prices(entries)
        print(f"\n[execute] Upsert: {result}")
        for c in recover:
            client.table("review_queue").update({"status": "approved"}).eq("id", c["id"]).execute()
        print(f"Marcados approved: {len(recover)}")

    # ---- Passo 1.5: archive-below + reject-false-positives (T1.3/T1.4) ----
    if args.archive_below is not None:
        if args.execute:
            count = archive_below_threshold(client, threshold=args.archive_below)
            print(f"\n[T1.3 archive-below {args.archive_below}] arquivados (rejected): {count}")
        else:
            print(
                f"\n[T1.3 archive-below {args.archive_below}] dry-run: use --execute "
                "para arquivar pendentes abaixo do threshold"
            )

    if args.reject_false_positives:
        if args.execute:
            count = reject_false_positives(client, ingredients)
            print(f"\n[T1.4 reject-false-positives] rejeitados: {count}")
        else:
            print(
                "\n[T1.4 reject-false-positives] dry-run: use --execute "
                "para rejeitar pendentes sem match"
            )

    # ---- Passo 2: cleanup / reject ----
    if args.delete_legacy:
        test_stores = ["Test Review Queue Store", "E2E Test Store", "Test Store", "OCR Test Store"]
        r = client.table("review_queue").delete().in_("store_name", test_stores).execute()
        print(f"\n[delete-legacy] Deletados de lojas de teste: {len(r.data or [])}")

    if args.reject_stores:
        # Lojas fora do escopo regional (descobertas via agregadores BR)
        out_of_scope = [
            "Zaffari",
            "Savegnago",
            "Sam's Club",
            "Pao de Acucar Fresh",
            "Extra Folheteria",
        ]
        for store in out_of_scope:
            r = (
                client.table("review_queue")
                .update({"status": "rejected"})
                .eq("store_name", store)
                .eq("status", "pending")
                .execute()
            )
            print(f"[reject-stores] {store}: {len(r.data or [])} rejeitados")

    # ---- Passo 3: resumo final ----
    remaining = (
        client.table("review_queue").select("store_name,status").eq("status", "pending").execute()
    )
    counts = Counter(item["store_name"] for item in (remaining.data or []))
    print("\n=== PENDENTES RESTANTES ===")
    for store, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {store:40s} {count}")
    print(f"  TOTAL: {len(remaining.data or [])}")


if __name__ == "__main__":
    main()