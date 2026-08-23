"""
Review Queue Service - Manages items awaiting manual approval.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from services.config_db import add_alias_to_ingredient, get_all_stores, get_store_by_name
from services.logger import logger
from services.supabase_client import get_service_client, get_supabase
from services.types import ReviewItem, Store

# Reabre itens rejeitados após este período (dias) — contexto pode ter mudado
_REOPEN_REJECTED_AFTER_DAYS = 90


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
            .select("id,status,reviewed_at")
            .eq("store_name", item.get("store_name", ""))
            .eq("raw_product", item["raw_product"])
            .execute()
        )
        if existing.data:
            row = existing.data[0]
            # Re-entry: UNIQUE(store_name, raw_product) impede reinserir. Se o
            # item foi REJEITADO há >= 90 dias, reabre como pending com o
            # contexto atual (marcas/thresholds podem ter mudado desde então).
            if row.get("status") == "rejected":
                reviewed_at = row.get("reviewed_at") or ""
                try:
                    reviewed_dt = datetime.fromisoformat(str(reviewed_at).replace("Z", "+00:00"))
                    age_days = (datetime.now(UTC) - reviewed_dt).days
                except ValueError:
                    age_days = -1
                if age_days >= _REOPEN_REJECTED_AFTER_DAYS:
                    client.table("review_queue").update(
                        {
                            "status": "pending",
                            "confidence": item.get("confidence", 0),
                            "suggestions": item.get("suggestions", []),
                            "match_reason": item.get("match_reason", ""),
                            "match_type": item.get("match_type", ""),
                            "top3": item.get("top3", []),
                            "brand": item.get("brand", ""),
                            "raw_price": item.get("raw_price"),
                            "validity_raw": item.get("validity_raw", ""),
                        }
                    ).eq("id", row["id"]).execute()
                    logger.info(
                        "review_queue: item rejeitado há %sd reaberto (re-entry): %s",
                        age_days,
                        str(item.get("raw_product", ""))[:60],
                    )
            return row
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
    """Retorna apenas itens PENDENTES (fix raiz: antes misturava approved/rejected)."""
    client = get_supabase()
    result = (
        client.table("review_queue")
        .select("*")
        .eq("status", "pending")
        .order("collected_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data if result.data else []


def get_review_queue_pending_count() -> int:
    """Contagem real de pendentes (independente do limit da página)."""
    client = get_supabase()
    result = client.table("review_queue").select("id", count="exact").eq("status", "pending").execute()
    return result.count or 0


def auto_approve_high_confidence(
    threshold: float = 0.80,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Aprova automaticamente itens pendentes com confiança >= threshold.

    Usa o candidato #1 do campo top3 (ou suggestions) como ingrediente alvo e
    delega ao approve_review_item (que resolve loja, insere preço e marca alias).
    Retorna estatísticas {candidates, approved, failed, skipped}.
    """
    client = get_supabase()
    query = (
        client.table("review_queue")
        .select("*")
        .eq("status", "pending")
        .gte("confidence", threshold)
        .order("collected_at", desc=True)
    )
    if limit:
        query = query.limit(limit)
    items = query.execute().data or []

    stats: dict[str, Any] = {"candidates": len(items), "approved": 0, "failed": 0, "skipped": 0}
    if dry_run:
        return stats

    for item in items:
        target = _pick_auto_approve_ingredient(item)
        if not target:
            stats["skipped"] += 1
            continue
        result = approve_review_item(item["id"], target, brand_override=item.get("brand", "") or "")
        if result and not result.get("error"):
            stats["approved"] += 1
        else:
            stats["failed"] += 1
    return stats


def _pick_auto_approve_ingredient(item: ReviewItem) -> str:
    """Escolhe o ingrediente do melhor candidato (top3[0] ou suggestions[0])."""
    top3 = item.get("top3") or []
    if isinstance(top3, str):
        import json

        try:
            top3 = json.loads(top3)
        except Exception:
            top3 = []
    if top3 and isinstance(top3, list):
        first = top3[0] or {}
        name = first.get("canonical_name") or ""
        if name:
            return name
    suggestions = item.get("suggestions") or []
    if isinstance(suggestions, str):
        import json

        try:
            suggestions = json.loads(suggestions)
        except Exception:
            suggestions = []
    if suggestions and isinstance(suggestions, list):
        first = suggestions[0]
        if isinstance(first, str) and first:
            return first
        if isinstance(first, dict):
            return first.get("canonical_name") or ""
    return ""


def _resolve_ingredient(ingredient_id: str) -> tuple[str, dict | None]:
    """Resolve ingredient_id para (ingredient_id_resolvido, ingredient_obj).

    Tenta: UUID → by_id → by_name → fuzzy match (score >= 70).
    """
    import re
    from rapidfuzz import fuzz
    from services.config_db import get_all_ingredients, get_ingredient_by_id, get_ingredient_by_name

    is_uuid = re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", ingredient_id, re.I)
    ingredient_obj = get_ingredient_by_id(ingredient_id) if is_uuid else None
    if not ingredient_obj:
        ingredient_obj = get_ingredient_by_name(ingredient_id)
    if not ingredient_obj:
        from rapidfuzz import fuzz

        best_score: float = 0.0
        best_ing = None
        norm_input = _normalize_text(ingredient_id)
        for ing in get_all_ingredients():
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
    return resolved_ingredient_id, ingredient_obj


def _fetch_review_item(item_id: str) -> dict | None:
    """Busca item na review_queue."""
    from services.supabase_client import get_service_client

    client = get_service_client()
    item = client.table("review_queue").select("*").eq("id", item_id).maybe_single().execute()
    return item.data if item and item.data else None


def _resolve_store(store_name: str) -> str:
    """Resolve store_id a partir do nome (exato → fuzzy)."""
    from rapidfuzz import fuzz

    if not store_name:
        return ""
    store_lookup = get_store_by_name(store_name)
    if not store_lookup:
        best_score = 0.0
        best_store = None
        for s in get_all_stores(include_inactive=True):
            score = fuzz.token_set_ratio(store_name, s.get("name", ""))
            if score > best_score:
                best_score = score
                best_store = s
        if best_score >= 80 and best_store:
            store_lookup = best_store
    return store_lookup.get("id", "") if store_lookup else ""


def _build_price_entry(item_data: dict, resolved_ingredient_id: str, store_id: str, brand_override: str = "") -> dict:
    """Constrói dict price_entry para upsert_price."""
    return {
        "ingredient_id": resolved_ingredient_id,
        "store_id": store_id,
        "source": item_data.get("source", "automated"),
        "store_name": item_data.get("store_name", ""),
        "raw_product": item_data.get("raw_product", ""),
        "raw_price": float(item_data.get("raw_price", 0)),
        "raw_unit": item_data.get("raw_unit", ""),
        "validity_raw": item_data.get("validity_raw", ""),
        "tier": 2,
        "confidence": float(item_data.get("confidence", 0.8)),
        "brand": item_data.get("brand", "") or "",
        "city": item_data.get("city", ""),
        "logistics": "pickup_local",
        "collected_at": item_data.get("collected_at"),
    }


def _auto_learn_alias(resolved_ingredient_id: str, price_entry: dict) -> None:
    """Auto-learning: adiciona alias se semantic similarity >= 0.75."""
    try:
        from services.config import get as get_config

        if not get_config("features.ai.auto_learning", True):
            return

        import json
        from parsers.semantic_matcher import get_matcher
        from services.config_db import get_ingredient_by_id, upsert_ingredient

        sm = get_matcher()
        ingredient_obj = get_ingredient_by_id(resolved_ingredient_id)
        if not ingredient_obj:
            return
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


def approve_review_item(item_id: str, ingredient_id: str, brand_override: str = "") -> dict[str, Any]:
    """Aprova item da review_queue: resolve ingredient/store, upsert price, auto-learning."""
    from services.supabase_client import get_service_client
    from services.price_repository import upsert_price

    client = get_service_client()

    # 1. Resolve ingredient
    resolved_ingredient_id, ingredient_obj = _resolve_ingredient(ingredient_id)
    if not resolved_ingredient_id:
        logger.warning("approve_review_item: ingredient '%s' not found in DB", ingredient_id)
        return {}

    # 2. Fetch review item
    item_data = _fetch_review_item(item_id)
    if not item_data:
        return {}

    # 3. Resolve store
    store_id = _resolve_store(item_data.get("store_name", ""))

    # 3. Build price entry
    price_entry = _build_price_entry(item_data, resolved_ingredient_id, store_id, brand_override)

    # 4. Upsert price (only if store resolved)
    if store_id:
        try:
            upsert_price(price_entry)
        except Exception as e:
            logger.error("approve_review_item upsert_price failed: %s", e)
            return {"error": f"Falha ao inserir preço: {e}"}

    # Add alias (always, if store + ingredient + product)
    if store_id and resolved_ingredient_id and price_entry.get("raw_product"):
        try:
            add_alias_to_ingredient(resolved_ingredient_id, price_entry["raw_product"])
        except Exception as e:
            logger.warning("approve_review_item add_alias failed: %s", e)

    # Auto-learning
    _auto_learn_alias(resolved_ingredient_id, price_entry)

    # Update review_queue status
    from services.supabase_client import get_service_client

    client = get_service_client()
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
