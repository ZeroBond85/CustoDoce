"""
Review Queue Service - Manages items awaiting manual approval.
"""

from services.logger import logger
from datetime import datetime, timedelta, UTC
from typing import Any
from services.supabase_client import get_supabase, get_service_client
from services.config_db import add_alias_to_ingredient, get_store_by_name, get_all_stores
from services.types import ReviewItem, Store


def _normalize_text(text: str) -> str:
    import unicodedata

    text = text.lower().strip()
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _fuzzy_find_store(store_name: str) -> Store | None:
    stores = get_all_stores(include_inactive=True)
    norm_name = _normalize_text(store_name)
    for s in stores:
        if _normalize_text(s.get("name", "")) == norm_name:
            return s
    for s in stores:
        if norm_name in _normalize_text(s.get("name", "")) or _normalize_text(s.get("name", "")) in norm_name:
            return s
    return None


def insert_review_item(item: ReviewItem) -> dict[str, Any]:
    client = get_service_client()
    try:
        existing = (
            client.table("review_queue")
            .select("id")
            .eq("store_name", item.get("store_name", ""))
            .eq("raw_product", item["raw_product"])
            .execute()
        )
        if existing.data:
            return existing.data[0]
    except Exception:
        logger.debug("insert_review_item dedup check failed", exc_info=True)
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
        "brand": item.get("brand", ""),
        "image_url": item.get("image_url", ""),
        "source_url": item.get("source_url", ""),
        "match_reason": item.get("match_reason", ""),
        "match_type": item.get("match_type", ""),
        "top3": item.get("top3", []),
    }
    try:
        result = client.table("review_queue").insert(data).execute()
        return result.data[0] if result.data else {}
    except Exception:
        return {}


def get_review_queue(limit: int = 500) -> list[ReviewItem]:
    client = get_supabase()
    result = client.table("review_queue").select("*").order("collected_at", desc=True).limit(limit).execute()
    return result.data if result.data else []


def approve_review_item(item_id: str, ingredient_id: str, brand_override: str = "") -> dict[str, Any]:
    from services.price_repository import upsert_price

    client = get_service_client()

    from services.config_db import get_ingredient_by_name, get_ingredient_by_id, get_all_ingredients
    import re

    is_uuid = re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", ingredient_id, re.I)
    ingredient_obj = get_ingredient_by_id(ingredient_id) if is_uuid else None
    if not ingredient_obj:
        ingredient_obj = get_ingredient_by_name(ingredient_id)
    if not ingredient_obj:
        from rapidfuzz import fuzz

        all_ing = get_all_ingredients()
        best_score = 0
        best_ing = None
        norm_input = _normalize_text(ingredient_id)
        for ing in all_ing:
            names = [ing.get("canonical_name", ""), ing.get("name", "")] + ing.get("aliases", [])
            for name in names:
                norm_name = _normalize_text(name)
                score = fuzz.token_set_ratio(norm_input, norm_name)
                if score > best_score:
                    best_score = score
                    best_ing = ing
        if best_score >= 70 and best_ing:
            ingredient_obj = best_ing
    resolved_ingredient_id = ingredient_obj.get("id", "") if ingredient_obj else ""

    if not resolved_ingredient_id:
        logger.warning("approve_review_item: ingredient '%s' not found in DB", ingredient_id)
        return {}

    item = client.table("review_queue").select("*").eq("id", item_id).maybe_single().execute()
    if item is None or not item.data:
        return {}

    store_name = item.data.get("store_name", "")
    store_lookup = get_store_by_name(store_name) if store_name else None
    if not store_lookup and store_name:
        store_lookup = _fuzzy_find_store(store_name)
    store_id = store_lookup.get("id", "") if store_lookup else ""

    price_entry = {
        "ingredient_id": resolved_ingredient_id,
        "store_id": store_id,
        "source": item.data.get("source", "automated"),
        "store_name": item.data.get("store_name", ""),
        "raw_product": item.data.get("raw_product", ""),
        "raw_price": float(item.data.get("raw_price", 0)),
        "raw_unit": item.data.get("raw_unit", ""),
        "validity_raw": item.data.get("validity_raw", ""),
        "tier": 2,
        "confidence": float(item.data.get("confidence", 0.8)),
        "brand": brand_override or item.data.get("brand", ""),
        "city": item.data.get("city", ""),
        "logistics": "pickup_local",
    }

    if store_id:
        try:
            upsert_price(price_entry)
        except Exception as e:
            logger.error("approve_review_item upsert_price failed: %s", e)
            return {"error": f"Falha ao inserir preço: {e}"}

    if store_id and resolved_ingredient_id and price_entry.get("raw_product"):
        try:
            add_alias_to_ingredient(resolved_ingredient_id, price_entry["raw_product"])
        except Exception as e:
            logger.warning("approve_review_item add_alias failed: %s", e)

    from services.config import get as get_config

    if get_config("features.ai.auto_learning", True):
        try:
            from parsers.semantic_matcher import get_matcher
            from services.config_db import get_ingredient_by_id, upsert_ingredient
            import json

            sm = get_matcher()
            ingredient_obj = get_ingredient_by_id(resolved_ingredient_id)
            if ingredient_obj:
                sim = sm.get_similarity(price_entry["raw_product"], ingredient_obj)
                if sim >= 0.75:
                    existing_aliases = ingredient_obj.get("aliases", [])
                    if isinstance(existing_aliases, str):
                        try:
                            existing_aliases = json.loads(existing_aliases)
                        except Exception:
                            existing_aliases = []
                    product_upper = price_entry["raw_product"].upper().strip()
                    if not any(a.upper().strip() == product_upper for a in existing_aliases):
                        existing_aliases.append(price_entry["raw_product"].strip())
                        upsert_ingredient({**ingredient_obj, "aliases": existing_aliases})
                        sm._ingredient_embeddings.pop(resolved_ingredient_id, None)
                        sm._ingredient_embeddings.pop(ingredient_obj.get("canonical_name", ""), None)
                        logger.info(
                            f"Auto-learning: novo alias '{price_entry['raw_product']}' para '{resolved_ingredient_id}'"
                        )
        except Exception as e:
            logger.warning("Auto-learning failed: %s", e)

    result = (
        client.table("review_queue")
        .update(
            {
                "status": "approved",
                "resolved_ingredient": resolved_ingredient_id,
                "reviewed_at": datetime.now(UTC).isoformat(),
            }
        )
        .eq("id", item_id)
        .execute()
    )

    return result.data[0] if result.data else {}


def reject_review_item(item_id: str) -> dict[str, Any]:
    client = get_service_client()
    try:
        result = client.table("review_queue").update({"status": "rejected"}).eq("id", item_id).execute()
        return result.data[0] if result.data else {}
    except Exception as e:
        logger.error("reject_review_item failed: %s", e)
        return {}


def auto_reject_stale_review_items(max_age_days: int = 7, min_confidence: float = 0.6) -> int:
    client = get_service_client()
    cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
    try:
        items = (
            client.table("review_queue")
            .select("id,confidence")
            .eq("status", "pending")
            .lt("collected_at", cutoff)
            .execute()
        )
        rejected = 0
        for item in items.data or []:
            conf = item.get("confidence", 0)
            if isinstance(conf, str):
                try:
                    conf = float(conf)
                except (ValueError, TypeError):
                    conf = 0
            if conf < min_confidence:
                client.table("review_queue").update({"status": "rejected"}).eq("id", item["id"]).execute()
                rejected += 1
        return rejected
    except Exception as e:
        logger.error("auto_reject_stale_review_items failed: %s", e)
        return 0
