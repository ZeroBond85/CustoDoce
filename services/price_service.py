from datetime import datetime, date
from typing import Optional

from services.supabase_client import get_supabase, get_service_client


def _weekday_pt(dt: datetime) -> str:
    dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
    return dias[dt.weekday()]


def _detect_promotion(raw_product: str, raw_unit: str) -> bool:
    import re
    text = f"{raw_product} {raw_unit}".lower()
    keywords = ["promo", "oferta", "promocao", "desconto", r"\d+%\s*off"]
    return any(re.search(k, text) for k in keywords)


def upsert_price(price_entry: dict) -> dict:
    client = get_service_client()
    now = datetime.utcnow()
    valid_until = price_entry.get("valid_until")
    if valid_until is None:
        valid_until = date.today().isoformat()
        from datetime import timedelta
        valid_until = (date.today() + timedelta(days=7)).isoformat()
    elif isinstance(valid_until, str):
        pass
    else:
        from datetime import timedelta
        valid_until = (date.today() + timedelta(days=7)).isoformat()

    is_promo = price_entry.get("is_promotion")
    if is_promo is None:
        is_promo = _detect_promotion(
            price_entry.get("raw_product", ""),
            price_entry.get("raw_unit", ""),
        )

    data = {
        "ingredient_id": price_entry["ingredient_id"],
        "store_id": price_entry["store_id"],
        "source": price_entry.get("source", "automated"),
        "store_name": price_entry.get("store_name", ""),
        "raw_product": price_entry["raw_product"],
        "raw_price": price_entry["raw_price"],
        "raw_unit": price_entry.get("raw_unit", ""),
        "collected_at": now.isoformat(),
        "valid_from": price_entry.get("valid_from", date.today().isoformat()),
        "valid_until": valid_until,
        "validity_raw": price_entry.get("validity_raw", ""),
        "collected_weekday": _weekday_pt(now),
        "is_promotion": is_promo,
        "tier": price_entry.get("tier"),
        "confidence": price_entry.get("confidence", 1.0),
        "normalized": price_entry.get("normalized"),
        "city": price_entry.get("city"),
        "logistics": price_entry.get("logistics"),
    }
    result = client.table("prices").upsert(
        data,
        on_conflict=["ingredient_id", "store_id", "collected_at"],
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
    valid_only: bool = True,
) -> list[dict]:
    client = get_supabase()
    query = client.table("prices").select("*")

    query = query.eq("ingredient_id", ingredient_canonical)

    if valid_only:
        today = date.today().isoformat()
        query = query.lte("valid_from", today)
        query = query.gte("valid_until", today)

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


def get_latest_prices(valid_only: bool = True) -> list[dict]:
    client = get_supabase()
    query = client.table("prices").select("*")

    if valid_only:
        today = date.today().isoformat()
        query = query.lte("valid_from", today)
        query = query.gte("valid_until", today)

    result = query.order("collected_at", desc=True).limit(500).execute()
    return result.data if result.data else []


def get_price_history(ingredient_canonical: str, days: int = 30, valid_only: bool = False) -> list[dict]:
    client = get_supabase()
    query = client.table("price_history").select("*").eq("ingredient_id", ingredient_canonical)

    if valid_only:
        today = date.today().isoformat()
        query = query.lte("valid_from", today).gte("valid_until", today)

    result = query.gte("collected_at", f"now() - interval '{days} days'").order("collected_at", desc=True).execute()
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
        "validity_raw": item.get("validity_raw", ""),
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
        "validity_raw": item.data.get("validity_raw", ""),
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
    return result.data[0] if result.data else []


def get_telegram_report(ingredients: list[dict], top_n: int = 5) -> list[dict]:
    messages = []
    for ing in ingredients:
        name = ing["canonical"]
        try:
            prices = get_prices_for_ingredient(name)
        except Exception:
            prices = []
        valid = [p for p in prices if p.get("normalized")
                 and isinstance(p["normalized"], dict)
                 and p["normalized"].get("price_per_kg", 0) > 0]
        valid.sort(key=lambda x: x["normalized"]["price_per_kg"])
        top = valid[:top_n]
        if top:
            messages.append({"ingredient": name, "prices": top})
    return messages
