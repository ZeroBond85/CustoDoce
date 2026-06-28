"""
Recipe Service - Management of confectionery recipes and their costing.
"""

from services.supabase_client import get_service_client


def upsert_recipe(recipe_data: dict) -> str:
    """Insert or update a recipe, return recipe_id."""
    client = get_service_client()
    data = {
        "name": recipe_data["name"],
        "yield_qty": recipe_data.get("yield_qty", 1),
        "overhead_pct": recipe_data.get("overhead_pct", 0),
        "profit_pct": recipe_data.get("profit_pct", 0),
    }
    try:
        result = client.table("recipes").upsert(data, on_conflict="name", returning="representation").execute()
        return result.data[0]["id"] if result.data else ""
    except Exception:
        result = client.table("recipes").insert(data, returning="representation").execute()
        return result.data[0]["id"] if result.data else ""


def upsert_recipe_item(item_data: dict) -> dict:
    """Insert or update a recipe item."""
    client = get_service_client()
    try:
        result = (
            client.table("recipe_items")
            .upsert(item_data, on_conflict="recipe_id,ingredient_id", returning="representation")
            .execute()
        )
        return result.data[0] if result.data else {}
    except Exception:
        result = client.table("recipe_items").insert(item_data, returning="representation").execute()
        return result.data[0] if result.data else {}
