"""
Dashboard Queries Service
Extracted from admin/app.py to separate query logic from UI.
All functions use cached Supabase clients for performance.
"""

from functools import lru_cache

from services.config_db import (
    get_active_ingredients,
    get_active_recipients,
    get_all_alert_rules,
    get_all_feature_flags,
    get_all_ingredients,
    get_all_recipients,
    get_all_schedules,
    get_all_stores,
    get_enabled_alert_rules,
    get_enabled_schedules,
)
from services.flyer_service import get_recent_flyers
from services.price_service import (
    get_all_current_prices,
    get_cheapest_prices,
    get_cross_ingredient_ranking,
    get_longitudinal_winners,
    get_price_history,
    get_price_trends,
    search_prices,
)
from services.supabase_client import get_supabase

# ============================================================
# Cached Data Loaders
# ============================================================


@lru_cache(maxsize=1)
def load_ingredients_yaml():
    import yaml

    with open("config/ingredients.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("ingredients", [])


@lru_cache(maxsize=1)
def load_stores_yaml():
    import yaml

    with open("config/stores.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("stores", [])


@lru_cache(maxsize=1)
def cached_get_all_stores(include_inactive=False):
    return get_all_stores(include_inactive)


@lru_cache(maxsize=1)
def cached_get_all_ingredients(include_inactive=False):
    return get_all_ingredients(include_inactive)


@lru_cache(maxsize=1)
def cached_get_all_schedules(include_disabled=False):
    return get_all_schedules(include_disabled)


@lru_cache(maxsize=1)
def cached_get_all_recipients(include_inactive=False):
    return get_all_recipients(include_inactive)


@lru_cache(maxsize=1)
def cached_get_all_alert_rules(include_disabled=False):
    return get_all_alert_rules(include_disabled)


@lru_cache(maxsize=1)
def cached_get_all_feature_flags():
    return get_all_feature_flags()


@lru_cache(maxsize=1)
def cached_get_active_ingredients():
    return get_active_ingredients()


@lru_cache(maxsize=1)
def cached_get_enabled_schedules():
    return get_enabled_schedules()


@lru_cache(maxsize=1)
def cached_get_active_recipients(channel=None):
    return get_active_recipients(channel)


@lru_cache(maxsize=1)
def cached_get_enabled_alert_rules(trigger=None):
    return get_enabled_alert_rules(trigger)


# ============================================================
# Price Queries (with caching)
# ============================================================


def get_prices_for_ingredient_cached(ingredient: str, valid_only: bool = True):
    """Get prices for an ingredient using the new server-side sorting."""
    return search_prices(ingredient, sort_by="price_per_kg", sort_order="asc", valid_only=valid_only)


def get_latest_prices_cached(valid_only: bool = True, limit: int = 2000):
    """Get latest prices using materialized view."""
    return get_all_current_prices(valid_only=valid_only, limit=limit)


def get_price_history_cached(ingredient: str, days: int = 30, valid_only: bool = False):
    return get_price_history(ingredient, days, valid_only)


def get_longitudinal_winners_cached(days: int = 90):
    return get_longitudinal_winners(days)


def get_price_trends_cached(ingredient: str, days: int = 90):
    return get_price_trends(ingredient, days)


def get_cross_ingredient_ranking_cached(days: int = 90):
    return get_cross_ingredient_ranking(days)


@lru_cache(maxsize=128)
def get_cheapest_prices_cached(ingredient: str, top_n: int = 3):
    return get_cheapest_prices(ingredient, top_n)


# ============================================================
# Store & Scraper Queries
# ============================================================


def get_stores_with_frequencies():
    """Get all stores with their scrape frequencies merged."""
    stores = cached_get_all_stores(include_inactive=True)
    freq_data = {}
    client = get_supabase()
    freq = client.table("scrape_frequencies").select("*").execute()
    for f in freq.data or []:
        freq_data[f["store_id"]] = f
    for s in stores:
        sid = s.get("id")
        if sid in freq_data:
            s["scrape_frequency"] = freq_data[sid]
    return stores


def get_active_stores_by_tier(tier: int | None = None):
    """Get active stores, optionally filtered by tier."""
    stores = cached_get_all_stores(include_inactive=False)
    if tier:
        stores = [s for s in stores if s.get("tier") == tier]
    return stores


def get_store_scraper_config(store_name: str):
    """Get scraper configuration for a store."""
    stores = cached_get_all_stores(include_inactive=True)
    for s in stores:
        if s.get("name") == store_name:
            return {
                "scraper": s.get("scraper"),
                "base_url": s.get("base_url"),
                "search_url": s.get("search_url"),
                "selectors": s.get("selectors"),
                "api_endpoint": s.get("api_endpoint"),
                "url_pattern": s.get("url_pattern"),
                "publish_day": s.get("publish_day"),
            }
    return None


# ============================================================
# Ingredient Queries
# ============================================================


def get_ingredients_with_brands():
    """Get ingredients with their brands and search terms."""
    return cached_get_all_ingredients(include_inactive=True)


def get_ingredient_by_canonical(canonical: str):
    """Find ingredient by canonical name."""
    ingredients = cached_get_all_ingredients(include_inactive=True)
    for ing in ingredients:
        if ing.get("canonical_name") == canonical:
            return ing
    return None


# ============================================================
# Flyer Queries
# ============================================================


def get_recent_flyers_cached(days: int = 7, source: str | None = None):
    return get_recent_flyers(days, source)


# ============================================================
# Analytics / Reporting Queries
# ============================================================


def get_dashboard_kpis():
    """Calculate KPIs for dashboard overview."""
    prices = get_latest_prices_cached(valid_only=True, limit=5000)
    if not prices:
        return {
            "total_prices": 0,
            "ingredients_covered": 0,
            "stores_active": 0,
            "avg_price_per_kg": 0,
        }

    ingredients = {p.get("ingredient_id", "") for p in prices}
    stores = {p.get("store_id", "") for p in prices}

    valid_ppk = [_safe_ppk(p) for p in prices if _safe_ppk(p) > 0]

    return {
        "total_prices": len(prices),
        "ingredients_covered": len(ingredients),
        "stores_active": len(stores),
        "avg_price_per_kg": sum(valid_ppk) / len(valid_ppk) if valid_ppk else 0,
    }


def get_coverage_by_ingredient():
    """Get coverage statistics per ingredient."""
    prices = get_latest_prices_cached(valid_only=True, limit=5000)
    if not prices:
        return []

    from collections import defaultdict

    coverage = defaultdict(lambda: {"stores": set(), "prices": 0, "min_ppk": float("inf"), "avg_ppk": 0})

    for p in prices:
        ing = p.get("ingredient_id", "")
        store = p.get("store_id", "")
        ppk = _safe_ppk(p)

        coverage[ing]["stores"].add(store)
        coverage[ing]["prices"] += 1
        if ppk > 0:
            coverage[ing]["min_ppk"] = min(coverage[ing]["min_ppk"], ppk)

    # Calculate averages
    for ing, data in coverage.items():
        ing_prices = [p for p in prices if p.get("ingredient_id") == ing]
        valid_ppk = [_safe_ppk(p) for p in ing_prices if _safe_ppk(p) > 0]
        data["avg_ppk"] = sum(valid_ppk) / len(valid_ppk) if valid_ppk else 0
        data["store_count"] = len(data["stores"])
        data["stores"] = list(data["stores"])

    return [{"ingredient": k, **v} for k, v in sorted(coverage.items())]


def get_active_promotions():
    """Get currently active promotions."""
    prices = get_latest_prices_cached(valid_only=True, limit=5000)
    promos = [p for p in prices if p.get("is_promotion")]
    return promos


# ============================================================
# Scraper Logs / Health Queries
# ============================================================


def get_recent_scraper_logs(limit: int = 50):
    client = get_supabase()
    result = client.table("scraping_logs").select("*").order("started_at", desc=True).limit(limit).execute()
    return result.data or []


def get_store_health():
    """Get health status for all stores based on recent logs."""
    client = get_supabase()
    logs = (
        client.table("scraping_logs")
        .select("store_name, status, started_at, finished_at, items_found, items_matched")
        .order("started_at", desc=True)
        .limit(200)
        .execute()
    )

    import statistics
    from collections import defaultdict

    health = defaultdict(
        lambda: {"runs": 0, "errors": 0, "total_found": 0, "total_matched": 0, "last_run": None, "latencies": []}
    )

    for log in logs.data or []:
        store = log.get("store_name", "")
        health[store]["runs"] += 1
        if log.get("status") in ("error", "failed"):
            health[store]["errors"] += 1
        health[store]["total_found"] += log.get("items_found", 0)
        health[store]["total_matched"] += log.get("items_matched", 0)
        if not health[store]["last_run"]:
            health[store]["last_run"] = log.get("started_at")

        started = log.get("started_at")
        completed = log.get("finished_at")
        if started and completed:
            try:
                from datetime import datetime

                start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(completed.replace("Z", "+00:00"))
                latency_ms = (end_dt - start_dt).total_seconds() * 1000
                health[store]["latencies"].append(latency_ms)
            except (ValueError, TypeError):
                pass

    result = []
    for store, data in health.items():
        success_rate = (data["runs"] - data["errors"]) / data["runs"] if data["runs"] > 0 else 0
        avg_items = data["total_found"] / data["runs"] if data["runs"] > 0 else 0
        latency_p95 = (
            statistics.quantiles(data["latencies"], n=20)[18]
            if len(data["latencies"]) >= 20
            else (max(data["latencies"]) if data["latencies"] else 0)
        )

        result.append(
            {
                "store_name": store,
                "last_run": data["last_run"],
                "success_rate": success_rate,
                "latency_p95_ms": latency_p95,
                "avg_items_per_run": avg_items,
                "total_runs": data["runs"],
                "error_count": data["errors"],
                "total_items": data["total_found"],
            }
        )

    return sorted(result, key=lambda x: x["last_run"] or "", reverse=True)


def get_store_coverage_health(stale_days: int = 3):
    """Visão de cobertura de PREÇOS por loja (não só sucesso do scraper).

    Cruza lojas ativas com os preços válidos mais recentes. Retorna, por loja:
    - last_price_date: data do preço mais recente coletado
    - days_since_price: há quantos dias (None se nunca coletou)
    - ingredients_covered: nº de ingredientes distintos com preço válido
    - is_stale: True se dias_since_price > stale_days (loja "sumiu" da coleta)
    - total_prices: nº de preços válidos atuais

    Isto dá visão no dia a dia de lojas que estão fora sem alarde
    (ex.: Tier 1 zerado por bug de flyer).
    """
    from datetime import UTC, datetime

    stores = cached_get_all_stores(include_inactive=False)
    prices = get_latest_prices_cached(valid_only=True, limit=5000)

    by_store: dict[str, dict] = {}
    for p in prices:
        sid = p.get("store_id", "")
        rec = by_store.setdefault(
            sid, {"last_price_date": None, "ingredients": set(), "total_prices": 0}
        )
        rec["total_prices"] += 1
        rec["ingredients"].add(p.get("ingredient_id", ""))
        pdate = p.get("valid_from") or p.get("collected_at")
        if pdate:
            try:
                dt = datetime.fromisoformat(str(pdate).replace("Z", "+00:00"))
                if rec["last_price_date"] is None or dt > rec["last_price_date"]:
                    rec["last_price_date"] = dt
            except (ValueError, TypeError):
                pass

    now = datetime.now(UTC)
    result = []
    for s in stores:
        sid = s.get("id")
        sname = s.get("name", "")
        rec = by_store.get(sid, {})
        days_since = None
        last_dt = rec.get("last_price_date")
        if last_dt:
            days_since = (now - last_dt).days
        result.append(
            {
                "store_id": sid,
                "store_name": sname,
                "tier": s.get("tier"),
                "last_price_date": last_dt.isoformat() if last_dt else None,
                "days_since_price": days_since,
                "ingredients_covered": len(rec.get("ingredients", set())),
                "total_prices": rec.get("total_prices", 0),
                "is_stale": (days_since is not None and days_since > stale_days) or (days_since is None),
            }
        )

    return sorted(result, key=lambda x: (x["is_stale"], x["days_since_price"] is None, -(x["days_since_price"] or 0)))


def get_coverage_summary(stale_days: int = 3):
    """Resumo de cobertura para banner de alerta no dashboard."""
    data = get_store_coverage_health(stale_days=stale_days)
    total = len(data)
    stale = sum(1 for d in data if d["is_stale"])
    no_price = sum(1 for d in data if d["total_prices"] == 0)
    fresh = sum(1 for d in data if not d["is_stale"])
    return {
        "total_stores": total,
        "fresh": fresh,
        "stale": stale,
        "no_price": no_price,
        "coverage_pct": round(100.0 * fresh / total, 1) if total else 0.0,
    }


def get_scraper_health_dashboard():
    """Get dashboard-ready scraper health with color-coded status."""
    data = get_store_health()
    for item in data:
        rate = item.get("success_rate", 0)
        if rate >= 0.95:
            item["status_label"] = "🟢 Healthy"
            item["status_color"] = "#10B981"
        elif rate >= 0.7:
            item["status_label"] = "🟡 Degraded"
            item["status_color"] = "#F59E0B"
        else:
            item["status_label"] = "🔴 Critical"
            item["status_color"] = "#EF4444"

        if item.get("latency_p95_ms", 0) > 60000:
            item["latency_label"] = "Slow (>1m)"
        elif item.get("latency_p95_ms", 0) > 30000:
            item["latency_label"] = "Moderate (>30s)"
        else:
            item["latency_label"] = "Fast"

    return data


# ============================================================
# Review Queue Queries
# ============================================================


def get_review_queue_cached(limit: int = 500):
    """Get review queue using service client for write operations if needed."""
    from services.price_service import get_review_queue

    return get_review_queue(limit)


def approve_review_item_cached(item_id: str, ingredient_id: str, brand_override: str = ""):
    from services.price_service import approve_review_item

    return approve_review_item(item_id, ingredient_id, brand_override)


def reject_review_item_cached(item_id: str):
    from services.price_service import reject_review_item

    return reject_review_item(item_id)


# ============================================================
# Utility
# ============================================================


def _safe_ppk(r: dict) -> float:
    """Extract price_per_kg with isinstance guard (normalized may be bool)."""
    norm = r.get("normalized")
    if isinstance(norm, dict):
        try:
            return float(norm.get("price_per_kg", 0))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def extract_ppk(row: dict) -> float:
    """Extract price_per_kg from a row, handling both nested and flat schemas.

    Sprint 8 fallback chain:
    1. ``row["price_per_kg"]`` (flat layout — v_latest_prices materialized view)
    2. ``row["normalized"]["price_per_kg"]`` (nested layout — price_history)
    Returns 0.0 if neither yields a positive numeric value.
    """
    flat = row.get("price_per_kg")
    if flat is not None:
        try:
            value = float(flat)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    norm = row.get("normalized", {})
    if isinstance(norm, dict):
        flat_top = norm.get("price_per_kg")
        if flat_top is not None:
            try:
                value = float(flat_top)
                if value > 0:
                    return value
            except (TypeError, ValueError):
                pass
    return 0.0


def extract_pun(row: dict) -> float:
    """Extract price_per_un from a row, handling both nested and flat schemas.

    Sprint 8 fallback chain:
    1. ``row["price_per_un"]`` (flat layout)
    2. ``row["normalized"]["price_per_un"]`` (nested layout)
    Returns 0.0 if neither yields a positive numeric value.
    """
    flat = row.get("price_per_un")
    if flat is not None:
        try:
            value = float(flat)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    norm = row.get("normalized", {})
    if isinstance(norm, dict):
        flat_top = norm.get("price_per_un")
        if flat_top is not None:
            try:
                value = float(flat_top)
                if value > 0:
                    return value
            except (TypeError, ValueError):
                pass
    return 0.0


def clear_all_caches():
    """Clear all LRU caches - useful after data mutations."""
    load_ingredients_yaml.cache_clear()
    load_stores_yaml.cache_clear()
    cached_get_all_stores.cache_clear()
    cached_get_all_ingredients.cache_clear()
    cached_get_all_schedules.cache_clear()
    cached_get_all_recipients.cache_clear()
    cached_get_all_alert_rules.cache_clear()
    cached_get_all_feature_flags.cache_clear()
    cached_get_active_ingredients.cache_clear()
    get_cheapest_prices_cached.cache_clear()
    cached_get_enabled_schedules.cache_clear()
    cached_get_active_recipients.cache_clear()
    cached_get_enabled_alert_rules.cache_clear()
