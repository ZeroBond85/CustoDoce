"""
Price Repository - Raw DB access for prices and price history.
"""

from datetime import UTC, date, datetime, timedelta
from contextlib import suppress
from typing import Any
import json
import re
import time

from services.logger import logger
from services.supabase_client import get_service_client, get_supabase, safe_execute, rpc_execute
from services.types import PriceEntry


def _weekday_pt(dt: datetime) -> str:
    dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
    return dias[dt.weekday()]


def _detect_promotion(raw_product: str, raw_unit: str) -> bool:
    text = f"{raw_product} {raw_unit}".lower()
    keywords = ["promo", "oferta", "promocao", "desconto", r"\d+%\s*off"]
    return any(re.search(k, text) for k in keywords)


def upsert_price(price_entry: PriceEntry) -> dict[str, Any]:
    client = get_service_client()
    collected_at = price_entry.get("collected_at", date.today().isoformat())
    try:
        collected_dt = datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
    except Exception:
        collected_dt = datetime.now(UTC)
    valid_until = price_entry.get("valid_until")
    if valid_until is None or not isinstance(valid_until, str):
        valid_until = (collected_dt.date() + timedelta(days=7)).isoformat()

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
        "p_collected_at": collected_at,
        "p_valid_from": price_entry.get("valid_from", collected_at),
        "p_valid_until": valid_until,
        "p_validity_raw": price_entry.get("validity_raw", ""),
        "p_collected_weekday": _weekday_pt(collected_dt),
        "p_is_promotion": is_promo,
        "p_tier": price_entry.get("tier"),
        "p_confidence": float(price_entry.get("confidence", 1.0)),
        "p_normalized": price_entry.get("normalized"),
        "p_city": price_entry.get("city"),
        "p_logistics": price_entry.get("logistics"),
        "p_brand": price_entry.get("brand", "Desconhecido"),
    }
    try:
        result = _upsert_price_rpc_with_retry(client, params)
        if isinstance(result, dict):
            return result
        if isinstance(result, list) and result:
            return result[0]
        return {}
    except Exception as e_rpc:
        logger.warning("upsert_price RPC failed, trying table fallback: %s", e_rpc)
        data = _build_price_row(price_entry)
        try:
            result = _upsert_price_table_with_retry(data)
            if isinstance(result, list) and result:
                return result[0]
            return {}
        except Exception as e_fallback:
            logger.error("upsert_price fallback failed: %s", e_fallback)
            raise e_fallback


def _build_price_row(price_entry: PriceEntry) -> dict[str, Any]:
    """Converte um PriceEntry no formato da tabela `prices` (fallback/batch)."""
    today = date.today().isoformat()
    valid_until = price_entry.get("valid_until")
    if valid_until is None or not isinstance(valid_until, str):
        valid_until = (date.today() + timedelta(days=7)).isoformat()
    is_promo = price_entry.get("is_promotion")
    if is_promo is None:
        is_promo = _detect_promotion(price_entry.get("raw_product", ""), price_entry.get("raw_unit", ""))
    return {
        "ingredient_id": price_entry["ingredient_id"],
        "store_id": price_entry["store_id"],
        "source": price_entry.get("source", "automated"),
        "store_name": price_entry.get("store_name", ""),
        "raw_product": price_entry["raw_product"],
        "raw_price": price_entry["raw_price"],
        "raw_unit": price_entry.get("raw_unit", ""),
        "collected_at": today,
        "valid_from": price_entry.get("valid_from", today),
        "valid_until": valid_until,
        "validity_raw": price_entry.get("validity_raw", ""),
        "collected_weekday": _weekday_pt(datetime.now(UTC)),
        "is_promotion": is_promo,
        "tier": price_entry.get("tier"),
        "confidence": float(price_entry.get("confidence", 1.0)),
        "normalized": price_entry.get("normalized"),
        "city": price_entry.get("city"),
        "logistics": price_entry.get("logistics"),
        "brand": price_entry.get("brand", "Desconhecido"),
    }


def _is_transient_net_err(exc: Exception) -> bool:
    """True se o erro é de rede/recurso transitório (não merece falha dura)."""
    s = str(exc)
    return (
        "Resource temporarily unavailable" in s
        or "Errno 11" in s
        or "timeout" in s.lower()
        or "Connection" in s
        or "reset by peer" in s
    )


def _upsert_price_rpc_with_retry(client: Any, params: dict[str, Any], max_retries: int = 3) -> list[dict[str, Any]]:
    """Chama upsert_price_rpc com retry em erros de rede/recurso transitórios."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return rpc_execute(client, "upsert_price_rpc", params)
        except Exception as exc:
            last_exc = exc
            if _is_transient_net_err(exc) and attempt < max_retries - 1:
                logger.info(
                    "upsert_price RPC transient error (attempt %d/%d), retrying: %s",
                    attempt + 1, max_retries, exc,
                )
                time.sleep(1.0 * (attempt + 1))
                continue
            raise
    assert last_exc is not None
    raise last_exc


def _upsert_price_table_with_retry(data: dict[str, Any] | list[dict[str, Any]], max_retries: int = 3) -> list[dict[str, Any]]:
    """Fallback via table.upsert com retry em erros de rede/recurso transitórios."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return safe_execute(
                get_service_client().table("prices")
                .upsert(data, on_conflict="ingredient_id,store_id,collected_at")
            )
        except Exception as exc:
            last_exc = exc
            if _is_transient_net_err(exc) and attempt < max_retries - 1:
                logger.info(
                    "upsert_price fallback transient error (attempt %d/%d), retrying: %s",
                    attempt + 1, max_retries, exc,
                )
                time.sleep(1.0 * (attempt + 1))
                continue
            raise
    assert last_exc is not None
    raise last_exc


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
    return safe_execute(query.limit(limit))


def get_latest_prices(valid_only: bool = True, limit: int = 2000) -> list[dict[str, Any]]:
    client = get_supabase()
    query = client.table("v_latest_prices").select("*")
    if valid_only:
        today = date.today().isoformat()
        query = query.lte("valid_from", today).gte("valid_until", today)
    return safe_execute(query.order("collected_at", desc=True).limit(limit))


def get_price_history(ingredient_canonical: str, days: int = 30, valid_only: bool = False) -> list[dict[str, Any]]:
    client = get_supabase()
    query = client.table("price_history").select("*").eq("ingredient_id", ingredient_canonical)
    if valid_only:
        today = date.today().isoformat()
        query = query.lte("valid_from", today).gte("valid_until", today)
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    return safe_execute(query.gte("collected_at", cutoff).order("collected_at", desc=True))


def _extract_price_per_kg(row: dict[str, Any]) -> float:
    """Menor custo por kg da row (normalized.price_per_kg > estimativa raw)."""
    norm = row.get("normalized")
    if isinstance(norm, dict):
        price_per_kg = norm.get("price_per_kg")
        if price_per_kg is not None:
            return float(price_per_kg)
    elif isinstance(norm, str):
        with suppress(Exception):
            price_per_kg = json.loads(norm).get("price_per_kg")
            if price_per_kg is not None:
                return float(price_per_kg)
    try:
        raw_price = float(row["raw_price"])
        raw_unit = row.get("raw_unit", "")
        m = re.search(r"(\d+)\s*x\s*([\d,.]+)\s*(kg|g)", raw_unit, re.I)
        if m:
            qty = int(m.group(1))
            weight = float(m.group(2).replace(",", "."))
            unit = m.group(3).lower()
            total_kg = qty * (weight if unit == "kg" else weight / 1000)
        else:
            m2 = re.search(r"([\d,.]+)\s*(kg|g)", raw_unit, re.I)
            if m2:
                weight = float(m2.group(1).replace(",", "."))
                unit = m2.group(2).lower()
                total_kg = weight if unit == "kg" else weight / 1000
            else:
                total_kg = 1.0
        if total_kg > 0:
            return raw_price / total_kg
    except (ValueError, TypeError, ZeroDivisionError):
        logger.debug("fallback price_per_kg estimate failed for row %s", row.get("ingredient_id"))
    return float("inf")


def _deduplicate_price_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicatas por (ingredient_id, store_id, collected_at), mantendo o melhor preço."""
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["ingredient_id"], row["store_id"], row["collected_at"])
        price_per_kg = _extract_price_per_kg(row)
        best = seen.get(key)
        if best is None or price_per_kg < _extract_price_per_kg(best):
            seen[key] = row
    return list(seen.values())


def batch_upsert_prices(price_entries: list[PriceEntry], chunk_size: int = 50) -> dict[str, int]:
    """Upsert em lote de preços na tabela `prices` via único `table.upsert`."""
    if not price_entries:
        return {"total": 0, "inserted": 0, "failed": 0}
    rows = [_build_price_row(e) for e in price_entries]
    rows = _deduplicate_price_rows(rows)
    inserted = 0
    failed = 0
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        try:
            result = _upsert_price_table_with_retry(chunk)
            if isinstance(result, list):
                inserted += len(result)
        except Exception as exc:
            failed += len(chunk)
            logger.warning("batch_upsert_prices chunk failed (%d rows): %s", len(chunk), exc)
    logger.info(
        "batch_upsert_prices: %d total, %d inserted, %d failed (%d chunks) [deduped from %d]",
        len(rows), inserted, failed, (len(rows) + chunk_size - 1) // chunk_size, len(price_entries),
    )
    return {"total": len(rows), "inserted": inserted, "failed": failed}
