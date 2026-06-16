from datetime import datetime
from typing import Optional

from services.supabase_client import get_supabase, get_service_client


def upsert_price(price_entry: dict) -> dict:
    client = get_service_client()
    data = {
        "ingredient_id": price_entry["ingredient_id"],
        "store_id": price_entry["store_id"],
        "source": price_entry.get("source", "automated"),
        "store_name": price_entry.get("store_name", ""),
        "raw_product": price_entry["raw_product"],
        "raw_price": price_entry["raw_price"],
        "raw_unit": price_entry.get("raw_unit", ""),
        "collected_at": datetime.utcnow().isoformat(),
        "valid_until": price_entry.get("valid_until"),
        "tier": price_entry.get("tier"),
        "confidence": price_entry.get("confidence", 1.0),
        "normalized": price_entry.get("normalized"),
        "city": price_entry.get("city"),
        "logistics": price_entry.get("logistics"),
    }
    result = client.table("prices").upsert(
        data,
        on_conflict=["ingredient_id", "store_id"],
        returning="representation",
    ).execute()
    return result.data[0] if result.data else {}


def search_prices(
    ingredient_canonical: str,
    sort_by: str = "price_per_kg",
    sort_order: str = "asc",
    limit: int = 50,
    tier: Optional[int] = None,
    logistics: Optional[str] = None,
    city: Optional[str] = None,
) -> list[dict]:
    client = get_supabase()
    query = client.table("prices").select("*")

    query = query.eq("ingredient_id", ingredient_canonical)
    query = query.order(sort_by, desc=(sort_order == "desc"))
    query = query.limit(limit)

    if tier:
        query = query.eq("tier", tier)

    if logistics:
        query = query.eq("logistics", logistics)

    if city:
        query = query.eq("city", city)

    result = query.execute()
    return result.data if result.data else []


def get_prices_for_ingredient(ingredient_canonical: str) -> list[dict]:
    return search_prices(ingredient_canonical, sort_by="price_per_kg", sort_order="asc")


def get_latest_prices() -> list[dict]:
    client = get_supabase()
    result = (
        client.table("prices")
        .select("*")
        .order("collected_at", desc=True)
        .limit(500)
        .execute()
    )
    return result.data if result.data else []


def get_price_history(ingredient_canonical: str, days: int = 30) -> list[dict]:
    client = get_supabase()
    result = (
        client.table("price_history")
        .select("*")
        .eq("ingredient_id", ingredient_canonical)
        .gte("collected_at", f"now() - interval '{days} days'")
        .order("collected_at", desc=True)
        .execute()
    )
    return result.data if result.data else []


def insert_review_item(item: dict) -> dict:
    client = get_service_client()
    data = {
        "raw_product": item["raw_product"],
        "raw_price": item.get("raw_price"),
        "raw_unit": item.get("raw_unit", ""),
        "store_name": item.get("store_name", ""),
        "source": item.get("source", "automated"),
        "confidence": item.get("confidence", 0),
        "suggestions": item.get("suggestions", []),
        "status": "pending",
    }
    result = client.table("review_queue").insert(data).execute()
    return result.data[0] if result.data else {}


def get_review_queue() -> list[dict]:
    client = get_supabase()
    result = (
        client.table("review_queue")
        .select("*")
        .order("collected_at", desc=True)
        .execute()
    )
    return result.data if result.data else []


def approve_review_item(item_id: str, ingredient_id: str) -> dict:
    client = get_service_client()
    item = (
        client.table("review_queue")
        .select("*")
        .eq("id", item_id)
        .single()
        .execute()
    )
    if not item.data:
        return {}

    result = (
        client.table("review_queue")
        .update({
            "status": "approved",
            "resolved_ingredient": ingredient_id,
            "reviewed_at": datetime.utcnow().isoformat(),
        })
        .eq("id", item_id)
        .execute()
    )

    price_entry = {
        "ingredient_id": ingredient_id,
        "store_id": item.data.get("store_name", "unknown").lower().replace(" ", "_"),
        "source": item.data.get("source", "automated"),
        "store_name": item.data.get("store_name", ""),
        "raw_product": item.data.get("raw_product", ""),
        "raw_price": float(item.data.get("raw_price", 0)),
        "raw_unit": item.data.get("raw_unit", ""),
        "tier": 2,
        "confidence": float(item.data.get("confidence", 0.8)),
    }
    upsert_price(price_entry)

    return result.data[0] if result.data else {}


def reject_review_item(item_id: str) -> dict:
    client = get_service_client()
    result = (
        client.table("review_queue")
        .update({"status": "rejected"})
        .eq("id", item_id)
        .execute()
    )
    return result.data[0] if result.data else {}
