"""
Recipe Service - Management of confectionery recipes and their costing.
"""

from typing import Any, cast

from services.supabase_client import get_service_client, safe_execute


def upsert_recipe(recipe_data: dict[str, Any]) -> str:
    """Insert or update a recipe, return recipe_id."""
    client = get_service_client()
    data = {
        "name": recipe_data["name"],
        "yield_qty": recipe_data.get("yield_qty", 1),
        "overhead_pct": recipe_data.get("overhead_pct", 0),
        "profit_pct": recipe_data.get("profit_pct", 0),
    }
    try:
        query = client.table("recipes").upsert(data, on_conflict="name", returning="representation")  # type: ignore[arg-type]
        res = safe_execute(query)
        return cast(str, res[0]["id"]) if res else ""
    except Exception:
        query = client.table("recipes").insert(data, returning="representation")  # type: ignore[arg-type]
        res = safe_execute(query)
        return cast(str, res[0]["id"]) if res else ""


def upsert_recipe_item(item_data: dict[str, Any]) -> dict[str, Any]:
    """Insert or update a recipe item."""
    client = get_service_client()
    try:
        query = client.table("recipe_items").upsert(item_data, on_conflict="recipe_id,ingredient_id", returning="representation")  # type: ignore[arg-type]
        res = safe_execute(query)
        return res[0] if res else {}
    except Exception:
        query = client.table("recipe_items").insert(item_data, returning="representation")  # type: ignore[arg-type]
        res = safe_execute(query)
        return res[0] if res else {}
