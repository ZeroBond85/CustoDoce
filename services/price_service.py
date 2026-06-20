import logging
from datetime import datetime, date, timedelta
from typing import Optional

from services.supabase_client import get_supabase, get_service_client
from services.config_db import add_alias_to_ingredient


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
        "collected_at": date.today().isoformat(),
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
        "brand": price_entry.get("brand", "Desconhecido"),
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

    if tier:
        query = query.eq("tier", tier)
    if logistics:
        query = query.eq("logistics", logistics)
    # Apply ordering to PostgREST query ONLY if sort_by is a direct column
    # and does NOT require client-side sorting.
    # We know 'price_per_kg' and 'price_per_un' are within 'normalized' JSONB,
    # so they require client-side sorting.
    if sort_by not in ("price_per_kg", "price_per_un", "raw_price"):
        # Apply database ordering if sort_by is a direct column
        query = query.order(sort_by, desc=(sort_order == "desc"))
    # If sort_by requires client-side sorting, we DON'T apply ordering here.
    # The 'collected_at' default ordering is also removed if client-side sort is needed.

    result = query.execute()
    data = result.data if result.data else []
    if not data:
        return []

    # Client-side sorting for price_per_kg, price_per_un, raw_price
    if sort_by in ("raw_price", "price_per_kg", "price_per_un"):
        reverse = sort_order == "desc"
        # For normalized fields, access them from the 'normalized' JSONB column
        if sort_by in ("price_per_kg", "price_per_un"):
            data.sort(key=lambda x: (x.get("normalized") or {}).get(sort_by, 0), reverse=reverse)
        else: # sort_by is "raw_price"
            data.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)
    # else: If sort_by was not client-side sortable, it would have been ordered by DB already.

    return data[:limit]


def get_prices_for_ingredient(ingredient_canonical: str) -> list[dict]:
    return search_prices(ingredient_canonical, sort_by="price_per_kg", sort_order="asc")


def get_latest_prices(valid_only: bool = True) -> list[dict]:
    client = get_supabase()
    query = client.table("prices").select("*")

    if valid_only:
        today = date.today().isoformat()
        query = query.lte("valid_from", today)
        query = query.gte("valid_until", today)

    result = query.order("collected_at", desc=True).limit(2000).execute()
    return result.data if result.data else []


def get_all_current_prices(valid_only: bool = True, limit: int = 2000) -> list[dict]:
    """Busca todos os precos de uma vez. Substitui N+1 loops de search_prices()."""
    client = get_supabase()
    query = client.table("prices").select("*")

    if valid_only:
        today = date.today().isoformat()
        query = query.lte("valid_from", today)
        query = query.gte("valid_until", today)

    result = query.order("collected_at", desc=True).limit(limit).execute()
    return result.data if result.data else []


def get_price_history(ingredient_canonical: str, days: int = 30, valid_only: bool = False) -> list[dict]:
    client = get_supabase()
    query = client.table("price_history").select("*").eq("ingredient_id", ingredient_canonical)

    if valid_only:
        today = date.today().isoformat()
        query = query.lte("valid_from", today).gte("valid_until", today)

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    result = query.gte("collected_at", cutoff).order("collected_at", desc=True).execute()
    return result.data if result.data else []


def insert_review_item(item: dict) -> dict:
    client = get_service_client()
    existing = client.table("review_queue").select("id")\
        .eq("store_name", item.get("store_name", ""))\
        .eq("raw_product", item["raw_product"])\
        .execute()
    if existing.data:
        return existing.data[0]
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
        "brand": item.data.get("brand", ""),
        "city": item.data.get("city", ""),
        "logistics": "pickup_local",
    }
    try:
        upsert_price(price_entry)
        # Add the raw_product as an alias to the ingredient for future exact matches
        if ingredient_id and price_entry.get('raw_product'):
            add_alias_to_ingredient(ingredient_id, price_entry['raw_product'])
    except Exception as e:
        logging.getLogger(__name__).error("approve_review_item upsert failed: %s", e)
        raise

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
    try:
        all_prices = get_all_current_prices(valid_only=True, limit=2000)
    except Exception:
        all_prices = []
    from collections import defaultdict
    by_ing = defaultdict(list)
    for p in all_prices:
        by_ing[p.get("ingredient_id", "")].append(p)
    for ing in ingredients:
        name = ing["canonical"]
        prices = by_ing.get(name, [])
        valid = [p for p in prices if p.get("normalized")
                 and isinstance(p["normalized"], dict)
                 and p["normalized"].get("price_per_kg", 0) > 0]
        valid.sort(key=lambda x: x["normalized"]["price_per_kg"])
        top = valid[:top_n]
        if top:
            messages.append({"ingredient": name, "prices": top})
    return messages


def cleanup_old_prices(retention_days: int = 90) -> dict:
    """Deleta preços mais antigos que retention_days (Supabase function)."""
    client = get_service_client()
    result = client.rpc("cleanup_old_prices", {"retention_days": retention_days}).execute()
    return {"deleted": result.data} if result.data else {"deleted": 0}


def cleanup_old_logs(retention_days: int = 30) -> dict:
    """Deleta scraping_logs mais antigos que retention_days."""
    client = get_service_client()
    result = client.rpc("cleanup_old_logs", {"retention_days": retention_days}).execute()
    return {"deleted": result.data} if result.data else {"deleted": 0}


def log_scraper_run(
    store_name: str,
    status: str = "completed",
    items_found: int = 0,
    items_matched: int = 0,
    errors: Optional[list] = None,
) -> dict:
    """Log scraper execution to scraping_logs table."""
    client = get_service_client()
    now = datetime.utcnow()
    data = {
        "store_name": store_name,
        "status": status,
        "started_at": now.isoformat(),
        "finished_at": now.isoformat(),
        "items_found": items_found,
        "items_matched": items_matched,
        "errors": errors or [],
    }
    result = client.table("scraping_logs").insert(data).execute()
    return result.data[0] if result.data else {}


def get_longitudinal_winners(days: int = 90) -> list[dict]:
    """Retorna contagem de vezes que cada loja foi a mais barata por ingrediente.

    Para cada ingrediente, em cada dia com dados, identifica a loja com menor
    price_per_kg e acumula um contador. Retorna lista de dicts:
    [{"ingredient_id": str, "store_name": str, "wins": int}, ...]
    """
    from datetime import timedelta
    client = get_supabase()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = (
        client.table("prices")
        .select("ingredient_id, store_name, raw_price, raw_unit, normalized, collected_at")
        .gte("collected_at", cutoff)
        .execute()
    )
    if not result.data:
        return []
    from collections import defaultdict
    daily: dict = defaultdict(lambda: defaultdict(list))
    for p in result.data:
        ing = p.get("ingredient_id", "")
        day = p.get("collected_at", "")[:10]
        norm = p.get("normalized") or {}
        ppk = norm.get("price_per_kg", 0) or 0
        if ppk <= 0:
            continue
        daily[ing][day].append({"store": p.get("store_name", "?"), "ppk": ppk})
    wins: dict = defaultdict(lambda: defaultdict(int))
    for ing, days_dict in daily.items():
        for day, entries in days_dict.items():
            if not entries:
                continue
            best = min(entries, key=lambda x: x["ppk"])
            wins[ing][best["store"]] += 1
    rows = []
    for ing, stores in wins.items():
        for store, count in stores.items():
            rows.append({"ingredient_id": ing, "store_name": store, "wins": count})
    rows.sort(key=lambda r: r["wins"], reverse=True)
    return rows


def get_price_trends(ingredient_id: str, days: int = 90) -> list[dict]:
    """Retorna média móvel de price_per_kg por dia para um ingrediente."""
    from datetime import timedelta
    client = get_supabase()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = (
        client.table("prices")
        .select("store_name, raw_price, normalized, collected_at")
        .eq("ingredient_id", ingredient_id)
        .gte("collected_at", cutoff)
        .execute()
    )
    if not result.data:
        return []
    from collections import defaultdict
    daily: dict = defaultdict(list)
    for p in result.data:
        day = p.get("collected_at", "")[:10]
        norm = p.get("normalized") or {}
        ppk = norm.get("price_per_kg", 0) or 0
        if ppk > 0:
            daily[day].append(ppk)
    trends = []
    for day in sorted(daily):
        vals = daily[day]
        trends.append({
            "date": day,
            "avg_ppk": round(sum(vals) / len(vals), 2),
            "min_ppk": round(min(vals), 2),
            "max_ppk": round(max(vals), 2),
            "store_count": len(vals),
        })
    return trends


def get_cheapest_prices(ingredient_id: str, top_n: int = 3) -> list[dict]:
    """Retorna os top N precos mais baratos (price_per_kg) para um ingrediente.

    Args:
        ingredient_id: Nome canonico do ingrediente
        top_n: Quantidade de resultados (default 3)

    Returns:
        Lista de dicts com os precos mais baratos, cada um contendo:
        store_name, raw_product, raw_price, raw_unit, price_per_kg,
        brand, is_promotion, valid_until, city, collected_at
    """
    prices = search_prices(
        ingredient_id,
        sort_by="price_per_kg",
        sort_order="asc",
        limit=top_n,
        valid_only=True,
    )
    return prices


def get_cross_ingredient_ranking(days: int = 90) -> list[dict]:
    """Retorna ranking de lojas por número de ingredientes onde são top-3."""
    from datetime import timedelta
    client = get_supabase()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = (
        client.table("prices")
        .select("ingredient_id, store_name, normalized, collected_at")
        .gte("collected_at", cutoff)
        .execute()
    )
    if not result.data:
        return []
    from collections import defaultdict
    per_ing: dict = defaultdict(list)
    for p in result.data:
        ing = p.get("ingredient_id", "")
        norm = p.get("normalized") or {}
        ppk = norm.get("price_per_kg", 0) or 0
        if ppk > 0:
            per_ing[ing].append({"store": p.get("store_name", "?"), "ppk": ppk})
    store_scores: dict = defaultdict(lambda: {"top1": 0, "top3": 0, "total": 0})
    for ing, entries in per_ing.items():
        sorted_entries = sorted(entries, key=lambda x: x["ppk"])
        seen = set()
        for rank, e in enumerate(sorted_entries, 1):
            if e["store"] in seen:
                continue
            seen.add(e["store"])
            store_scores[e["store"]]["total"] += 1
            if rank == 1:
                store_scores[e["store"]]["top1"] += 1
            if rank <= 3:
                store_scores[e["store"]]["top3"] += 1
    rows = []
    for store, scores in store_scores.items():
        rows.append({
            "store_name": store,
            "top1_count": scores["top1"],
            "top3_count": scores["top3"],
            "total_ingredients": scores["total"],
        })
    rows.sort(key=lambda r: (r["top1_count"], r["top3_count"]), reverse=True)
    return rows
