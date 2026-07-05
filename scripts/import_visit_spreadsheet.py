import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.price_service import upsert_price
from parsers.matcher import load_ingredients_yaml
from parsers.normalizer import normalize_price


def import_spreadsheet(filepath: str) -> int:
    df = pd.read_excel(filepath)
    expected = ["store_name", "city", "ingredient_id", "raw_product", "raw_price", "raw_unit", "visit_date", "notes"]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        print(f"Colunas ausentes: {missing}")
        return 0

    ingredients = load_ingredients_yaml()
    canonical_names = {i["canonical"].lower(): i for i in ingredients}

    imported = 0
    for _, row in df.iterrows():
        store_name = str(row.get("store_name", "")).strip()
        raw_product = str(row.get("raw_product", "")).strip()
        raw_price_raw = row.get("raw_price")
        raw_unit = str(row.get("raw_unit", "")).strip()
        ingredient_raw = str(row.get("ingredient_id", "")).strip()

        if not all([store_name, raw_product, raw_price_raw, ingredient_raw]):
            continue

        try:
            raw_price = float(raw_price_raw)
        except (ValueError, TypeError):
            print(f"  Preço inválido: {raw_price_raw}")
            continue

        match = canonical_names.get(ingredient_raw.lower())
        if not match:
            print(f"  Ingrediente não encontrado: {ingredient_raw}")
            continue

        normalized = normalize_price(raw_price, raw_unit)
        entry = {
            "ingredient_id": match["canonical"],
            "store_id": store_name.lower().replace(" ", "_"),
            "source": "manual_visit",
            "store_name": store_name,
            "raw_product": raw_product,
            "raw_price": raw_price,
            "raw_unit": raw_unit,
            "collected_at": row.get("visit_date") or date.today().isoformat(),
            "tier": 2,
            "confidence": 1.0,
            "normalized": normalized.to_dict() if normalized else None,
            "city": str(row.get("city", "")).strip() or "São Paulo",
            "logistics": "pickup_sp",
        }
        upsert_price(entry)
        imported += 1

    return imported


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python import_visit_spreadsheet.py <caminho_para_planilha.xlsx>")
        sys.exit(1)

    filepath = sys.argv[1]
    if not Path(filepath).exists():
        print(f"Arquivo não encontrado: {filepath}")
        sys.exit(1)

    total = import_spreadsheet(filepath)
    print(f"{total} preços importados com sucesso.")
