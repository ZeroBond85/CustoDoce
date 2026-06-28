"""
Import Service - Handles manual data import (Tier 2b/4) from files.
"""

import pandas as pd
from typing import Any
from datetime import datetime

from services.logger import logger
from services.config_db import get_all_ingredients, get_all_stores
from services.price_service import upsert_price
from parsers.normalizer import normalize_price


def import_manual_prices(file_path: str) -> dict[str, Any]:
    """
    Imports prices from an Excel or CSV file.
    Expected columns: ingredient, store, price, unit, collected_at, brand
    """
    try:
        if file_path.endswith(".csv"):
            df = pd.read_csv(file_path)
        elif file_path.endswith((".xls", ".xlsx")):
            df = pd.read_excel(file_path)
        else:
            raise ValueError("Unsupported file format. Use CSV or XLSX.")

        ingredients = {ing["canonical_name"]: ing["id"] for ing in get_all_ingredients()}
        stores = {s["name"]: s["id"] for s in get_all_stores()}

        imported_count = 0
        errors = []

        for index, row in df.iterrows():
            try:
                ing_name = str(row.get("ingredient", "")).strip()
                store_name = str(row.get("store", "")).strip()
                raw_price = float(row.get("price", 0))
                raw_unit = str(row.get("unit", ""))
                collected_at = str(row.get("collected_at", ""))
                brand = str(row.get("brand", ""))

                if ing_name not in ingredients:
                    errors.append(f"Row {index + 2}: Ingredient '{ing_name}' not found in DB")
                    continue
                if store_name not in stores:
                    errors.append(f"Row {index + 2}: Store '{store_name}' not found in DB")
                    continue

                norm = normalize_price(raw_price, raw_unit)

                entry = {
                    "ingredient_id": ingredients[ing_name],
                    "store_id": stores[store_name],
                    "store_name": store_name,
                    "raw_product": f"{ing_name} - Manual Import",
                    "raw_price": raw_price,
                    "raw_unit": raw_unit,
                    "collected_at": collected_at if collected_at else datetime.now().date().isoformat(),
                    "brand": brand,
                    "normalized": norm.to_dict() if norm else None,
                    "tier": 4 if "Manual" in store_name else 2,  # Simplified tier logic
                    "confidence": 1.0,
                }

                upsert_price(entry)
                imported_count += 1
            except Exception as e:
                errors.append(f"Row {index + 2}: {str(e)}")

        return {"imported": imported_count, "errors": errors}
    except Exception as e:
        logger.error("Import failed: %s", e)
        return {"imported": 0, "errors": [str(e)]}
