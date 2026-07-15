"""
Price Repository - Raw DB access for prices and price history.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from services.logger import logger
from services.supabase_client import get_service_client, get_supabase
from services.types import PriceEntry


def _weekday_pt(dt: datetime) -> str:
    dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
    return dias[dt.weekday()]


def _detect_promotion(raw_product: str, raw_unit: str) -> bool:
    import re

    text = f"{raw_product} {raw_unit}".lower()
    keywords = ["promo", "oferta", "promocao", "desconto", r"\d+%\s*off"]
    return any(re.search(k, text) for k in keywords)


def upsert_price(price_entry: PriceEntry) -> dict[str, Any]:
    import time as _time

    client = get_service_client()
    now = datetime.now(UTC)
    valid_until = price_entry.get("valid_until")
    if valid_until is None or not isinstance(valid_until, str):
        valid_until = (date.today() + timedelta(days=7)).isoformat()

    is_promo = price_entry.get("is_promotion")
    if is_promo is None:
        is_promo = _detect_promotion(
            price_entry.get("raw_product", ""),
            price_entry.get("raw_unit", ""),
        )

    params = {
        "p_ingredient_id": price_entry["ingredient_id"],
        "p_store_id": price_entry["store_id"],
        "p_source": price_entry.get("source", "automated"),
        "p_store_name": price_entry.get("store_name", ""),
        "p_raw_product": price_entry["raw_product"],
        "p_raw_price": float(price_entry["raw_price"]),
        "p_raw_unit": price_entry.get("raw_unit", ""),
        "p_collected_at": date.today().isoformat(),
        "p_valid_from": price_entry.get("valid_from", date.today().isoformat()),
        "p_valid_until": valid_until,
        "p_validity_raw": price_entry.get("validity_raw", ""),
        "p_collected_weekday": _weekday_pt(now),
        "p_is_promotion": is_promo,
        "p_tier": price_entry.get("tier"),
        "p_confidence": float(price_entry.get("confidence", 1.0)),
        "p_normalized": price_entry.get("normalized"),
        "p_city": price_entry.get("city"),
        "p_logistics": price_entry.get("logistics"),
        "p_brand": price_entry.get("brand", "Desconhecido"),
    }
    try:
        result = client.rpc("upsert_price_rpc", params).execute()
        data = result.data
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data:
            return data[0]
        return {}
    except Exception as e_rpc:
        logger.warning("upsert_price RPC failed, trying table fallback: %s", e_rpc)
        today = date.today().isoformat()
        ingredient_id = price_entry["ingredient_id"]
        store_id = price_entry["store_id"]
        data = {
            "ingredient_id": ingredient_id,
            "store_id": store_id,
            "source": price_entry.get("source", "automated"),
            "store_name": price_entry.get("store_name", ""),
            "raw_product": price_entry["raw_product"],
            "raw_price": price_entry["raw_price"],
            "raw_unit": price_entry.get("raw_unit", ""),
            "collected_at": today,
            "valid_from": price_entry.get("valid_from", today),
            "valid_until": valid_until,
            "validity_raw": price_entry.get("validity_raw", ""),
            "collected_weekday": _weekday_pt(now),
            "is_promotion": is_promo,
            "tier": price_entry.get("tier"),
            "confidence": price_entry.get("confidence", 1.0),
            "normalized": price_entry.get("normalized"),
            "city": price_entry.get("city"),
            "logistics": price_entry.get("logistics"),
            "brand": price_entry.get("brand", "Desconhecido"),
        }
        try:
            existing = (
                client.table("prices")
                .select("id")
                .eq("ingredient_id", ingredient_id)
                .eq("store_id", store_id)
                .eq("collected_at", today)
                .maybe_single()
                .execute()
            )
            if existing and existing.data:
                result = client.table("prices").update(data).eq("id", existing.data["id"]).execute()
            else:
                result = client.table("prices").insert(data).execute()
            return result.data[0] if result.data else {}
        except Exception as e_fallback:
            if "Resource temporarily unavailable" in str(e_fallback):
                logger.warning("upsert_price fallback failed (resource exhaustion), retrying in 2s: %s", e_fallback)
                _time.sleep(2)
                try:
                    result = client.table("prices").insert(data).execute()
                    return result.data[0] if result.data else {}
                except Exception as e_retry:
                    logger.error("upsert_price retry also failed: %s", e_retry)
                    raise e_retry
            else:
                logger.error("upsert_price fallback failed: %s", e_fallback)
                raise e_fallback


def search_prices(
    ingredient_canonical: str,
    sort_by: str = "price_per_kg",
    sort_order: str = "asc",
    limit: int = 50,
    tier: int | None = None,
    logistics: str | None = None,
    city: str | None = None,
    valid_only: bool = True,
) -> list[dict[str, Any]]:
    client = get_supabase()
    query = client.table("prices").select("*")
    query = query.eq("ingredient_id", ingredient_canonical)
    if valid_only:
        today = date.today().isoformat()
        query = query.lte("valid_from", today)
        query = query.gte("valid_until", today)
    if tier:
        query = query.eq("tier", tier)
    if logistics:
        query = query.eq("logistics", logistics)
    if city:
        query = query.eq("city", city)
    if sort_by in ("price_per_kg", "price_per_un"):
        query = query.order(sort_by, desc=(sort_order == "desc"))
    elif sort_by == "raw_price":
        query = query.order("raw_price", desc=(sort_order == "desc"))
    else:
        query = query.order(sort_by, desc=(sort_order == "desc"))
    result = query.limit(limit).execute()
    return result.data if result.data else []


def get_latest_prices(valid_only: bool = True, limit: int = 2000) -> list[dict[str, Any]]:
    client = get_supabase()
    query = client.table("v_latest_prices").select("*")
    if valid_only:
        today = date.today().isoformat()
        query = query.lte("valid_from", today).gte("valid_until", today)
    result = query.order("collected_at", desc=True).limit(limit).execute()
    return result.data if result.data else []


def get_price_history(ingredient_canonical: str, days: int = 30, valid_only: bool = False) -> list[dict[str, Any]]:
    client = get_supabase()
    query = client.table("price_history").select("*").eq("ingredient_id", ingredient_canonical)
    if valid_only:
        today = date.today().isoformat()
        query = query.lte("valid_from", today).gte("valid_until", today)
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    result = query.gte("collected_at", cutoff).order("collected_at", desc=True).execute()
    return result.data if result.data else []
