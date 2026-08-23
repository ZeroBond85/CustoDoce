#!/usr/bin/env python3
"""Gera candidatos de marca a partir do DB de produção.

Uso:
  python scripts/generate_brand_candidates.py --output brand_candidates.yaml
  python scripts/generate_brand_candidates.py --dry-run

Output: YAML com sugestões de marcas por ingrediente (top-N por frequência).
"""

import argparse
import sys
from collections import Counter

from parsers.brand_extractor import extract_brand
from services.supabase_client import get_service_client


def fetch_all_ingredients():
    """Busca todos os ingredientes ativos com suas marcas atuais."""
    client = get_service_client()
    r = client.rpc("exec_sql_query", {
        "sql": "SELECT canonical_name, brands FROM ingredients WHERE active = true"
    }).execute()
    return {row["canonical_name"]: row["brands"] or [] for row in r.data or []}


def fetch_raw_products_per_ingredient(limit_per_ing: int = 200):
    """Para cada ingrediente, busca raw_products únicos com frequência."""
    client = get_service_client()
    sql = """
        SELECT ingredient_id, raw_product, COUNT(*) as freq
        FROM prices
        WHERE ingredient_id IS NOT NULL AND raw_product IS NOT NULL
        GROUP BY ingredient_id, raw_product
        ORDER BY ingredient_id, freq DESC
    """
    r = client.rpc("exec_sql_query", {"sql": sql}).execute()

    by_ing = {}
    for row in r.data or []:
        by_ing.setdefault(row["ingredient_id"], []).append((row["raw_product"], row["freq"]))

    # Limita top-N por ingrediente
    for ing, lst in by_ing.items():
        by_ing[ing] = lst[:limit_per_ing]
    return by_ing


def generate_candidates(ingredients: dict, raw_by_ing: dict) -> dict:
    """Para cada ingrediente, extrai marca de cada raw_product e conta."""
    all_ings_list = [{"canonical_name": k, "brands": v} for k, v in ingredients.items()]

    suggestions = {}
    for ing_id, raw_list in raw_by_ing.items():
        if ing_id not in ingredients:
            continue  # ingrediente não está no config (pode ser teste/lixo)
        counter = Counter()
        for raw_product, freq in raw_list:
            brand = extract_brand(raw_product, {"brands": ingredients[ing_id]}, all_ingredients=all_ings_list)
            if brand and brand != "Desconhecido":
                counter[brand] += freq
        # Ordena por frequência
        suggestions[ing_id] = sorted(counter.items(), key=lambda x: x[1], reverse=True)
    return suggestions


def print_suggestions(suggestions: dict, ingredients: dict, top_n: int = 10):
    for ing, brands in suggestions.items():
        current = ingredients.get(ing, [])
        print(f"\n# {ing} (atuais: {current})")
        for brand, freq in brands[:top_n]:
            status = "[OK]" if brand in current else "-> ADD"
        print(f"  {brand:25s}  ({freq:4d}x) {status}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Só imprime sugestões")
    parser.add_argument("--top-n", type=int, default=10, help="Top N marcas por ingrediente")
    parser.add_argument("--limit-per-ing", type=int, default=200, help="Limite raw_products por ingrediente")
    args = parser.parse_args()

    print("Buscando ingredientes ativos...")
    ingredients = fetch_all_ingredients()
    print(f"  {len(ingredients)} ingredientes ativos")

    print("Buscando raw_products do DB...")
    raw_by_ing = fetch_raw_products_per_ingredient(args.limit_per_ing)
    print(f"  {len(raw_by_ing)} ingredientes com preços")

    print("Gerando candidatos...")
    suggestions = generate_candidates(ingredients, raw_by_ing)

    print_suggestions(suggestions, ingredients, args.top_n)

    # TODO: output YAML patch format
    if args.dry_run:
        return 0

    print("\n[Dry-run only: use --dry-run to just preview]")
    return 0


if __name__ == "__main__":
    sys.exit(main())