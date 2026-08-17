"""
Dashboard Queries Service
Extracted from admin/app.py to separate query logic from UI.
All functions use cached Supabase clients for performance.
"""

from contextlib import suppress
from datetime import UTC, datetime
from functools import lru_cache

from services.logger import logger

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
# Cache híbrido: @st.cache_data em runtime Streamlit, fallback local fora dele
# ============================================================


def _streamlit_runtime_active() -> bool:
    """True se este processo roda DENTRO de um runtime Streamlit (script do dashboard).

    Em scripts/telegram/testes unitários o Streamlit pode estar instalado mas sem
    runtime ativo (``st.runtime.exists() is False``). Nesses casos o cache local
    (lru_cache/thread-safe) é usado — comportamento anterior preservado.
    """
    try:
        import streamlit as st

        if getattr(st, "runtime", None) is not None:
            return bool(st.runtime.exists())
    except Exception:  # noqa: BLE001 - streamlit ausente/falho => fallback local
        logger.debug("Streamlit runtime check falhou — fallback para cache local")
    return False


# Registro das funções cacheadas para clear_all_caches() percorrer ambos os tipos.
_CACHE_REGISTRY: list[object] = []


def _register(fn: object) -> None:
    if fn not in _CACHE_REGISTRY:
        _CACHE_REGISTRY.append(fn)


def dashboard_cache(ttl: int | None = None, maxsize: int = 1):
    """Decorator: @st.cache_data(ttl=...) dentro do Streamlit; lru_cache fora.

    O dashboard roda em processo Streamlit persistente onde ``@lru_cache`` nunca
    expira (preços viram stale para sempre) e não é limpo pelo botão "Limpar
    Cache" (``st.cache_data.clear()`` em layout.py). ``@st.cache_data`` resolve
    TTL + limpeza global. Fora do runtime cai em ``lru_cache`` — scripts,
    telegram e testes unitários mantêm o comportamento atual.
    """
    def decorator(func):
        if _streamlit_runtime_active():
            import streamlit as st

            cached = st.cache_data(ttl=ttl)(func)
            _register(cached)
            return cached
        cached = lru_cache(maxsize=maxsize)(func)
        _register(cached)
        return cached

    return decorator


def dashboard_data_cache(ttl: int | None = None):
    """Decorator para dados DINÂMICOS (preços): st.cache_data no runtime, sem cache fora.

    Diferente de ``dashboard_cache`` (config estática), dados de preço NÃO podem
    ter cache local em scripts/testes: o mock/patch do Supabase mudaria e o
    lru_cache devolveria resultado velho. Aqui, fora do Streamlit o decorator é
    identidade (sem cache); dentro, ``st.cache_data`` com TTL.
    """
    def decorator(func):
        if _streamlit_runtime_active():
            import streamlit as st

            cached = st.cache_data(ttl=ttl)(func)
            _register(cached)
            return cached
        return func

    return decorator


def _clear_cached_functions() -> None:
    """Limpa cache de todas as funções registradas (lru_cache e st.cache_data)."""
    for fn in _CACHE_REGISTRY:
        clear = getattr(fn, "cache_clear", None)
        if callable(clear):
            with suppress(Exception):
                clear()

# ============================================================
# Cached Data Loaders
# ============================================================


@dashboard_cache(ttl=3600)
def load_ingredients_yaml():
    import yaml

    with open("config/ingredients.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("ingredients", [])


@dashboard_cache(ttl=3600)
def load_stores_yaml():
    import yaml

    with open("config/stores.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("stores", [])


@dashboard_cache(ttl=300)
def cached_get_all_stores(include_inactive=False):
    return get_all_stores(include_inactive)


@dashboard_cache(ttl=300)
def cached_get_all_ingredients(include_inactive=False):
    return get_all_ingredients(include_inactive)


@dashboard_cache(ttl=300)
def cached_get_all_schedules(include_disabled=False):
    return get_all_schedules(include_disabled)


@dashboard_cache(ttl=300)
def cached_get_all_recipients(include_inactive=False):
    return get_all_recipients(include_inactive)


@dashboard_cache(ttl=300)
def cached_get_all_alert_rules(include_disabled=False):
    return get_all_alert_rules(include_disabled)


@dashboard_cache(ttl=300)
def cached_get_all_feature_flags():
    return get_all_feature_flags()


@dashboard_cache(ttl=300)
def cached_get_active_ingredients():
    return get_active_ingredients()


@dashboard_cache(ttl=300)
def cached_get_enabled_schedules():
    return get_enabled_schedules()


@dashboard_cache(ttl=300)
def cached_get_active_recipients(channel=None):
    return get_active_recipients(channel)


@dashboard_cache(ttl=300)
def cached_get_enabled_alert_rules(trigger=None):
    return get_enabled_alert_rules(trigger)


# ============================================================
# Price Queries (with caching)
# ============================================================


@dashboard_data_cache(ttl=600)
def get_prices_for_ingredient_cached(ingredient: str, valid_only: bool = True, tier: int | None = None):
    """Get prices for an ingredient using the new server-side sorting.

    Filtra por ingrediente (e tier, quando informado) no PostgREST — o dashboard
    não baixa mais 5000 preços de todos os ingredientes para mostrar um só.
    """
    return search_prices(
        ingredient, sort_by="price_per_kg", sort_order="asc", valid_only=valid_only, tier=tier
    )


@dashboard_data_cache(ttl=600)
def get_latest_prices_cached(valid_only: bool = True, limit: int = 2000):
    """Get latest prices using materialized view."""
    return get_all_current_prices(valid_only=valid_only, limit=limit)


@dashboard_data_cache(ttl=600)
def get_price_history_cached(ingredient: str, days: int = 30, valid_only: bool = False):
    return get_price_history(ingredient, days, valid_only)


@dashboard_data_cache(ttl=600)
def get_longitudinal_winners_cached(days: int = 90):
    return get_longitudinal_winners(days)


@dashboard_data_cache(ttl=600)
def get_price_trends_cached(ingredient: str, days: int = 90):
    return get_price_trends(ingredient, days)


@dashboard_data_cache(ttl=600)
def get_cross_ingredient_ranking_cached(days: int = 90):
    return get_cross_ingredient_ranking(days)


@dashboard_cache(maxsize=128)
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


def get_active_stores() -> dict[str, str]:
    """Get active stores as dict of name -> id."""
    stores = cached_get_all_stores(include_inactive=False)
    return {s["name"]: s["id"] for s in stores}


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
    return _kpis_from_prices(prices)


def _kpis_from_prices(prices):
    """KPIs a partir de preços já carregados — dashboard reusa 1 query de 5000."""
    if not prices:
        return {
            "total_prices": 0,
            "ingredients_covered": 0,
            "stores_active": 0,
            "avg_price_per_kg": 0,
        }

    ingredients = {p.get("ingredient_id", "") for p in prices}
    stores = {p.get("store_id", "") for p in prices}

    # Single-pass: _safe_ppk chamado 1x por item (antes 2x no filter+listcomp).
    total_ppk = 0.0
    valid_count = 0
    for p in prices:
        ppk = _safe_ppk(p)
        if ppk > 0:
            total_ppk += ppk
            valid_count += 1

    return {
        "total_prices": len(prices),
        "ingredients_covered": len(ingredients),
        "stores_active": len(stores),
        "avg_price_per_kg": total_ppk / valid_count if valid_count else 0,
    }


def get_coverage_by_ingredient():
    """Get coverage statistics per ingredient.

    Single-pass O(N) sobre os preços — evita o loop O(N²) anterior
    (um `filter` sobre a lista inteira por ingrediente) que degradava
    com ~5000 preços × 23 ingredientes.
    """
    prices = get_latest_prices_cached(valid_only=True, limit=5000)
    return _coverage_from_prices(prices)


def _coverage_from_prices(prices):
    """Computa cobertura por ingrediente a partir de preços já carregados.

    Expor a versão com preços prontos permite que o dashboard faça UMA query
    de preços e reutilize o resultado em cobertura + outliers + ofertas (em vez
    de N queries de 5000 rows). Semântica idêntica à versão com query interna.
    """
    if not prices:
        return []

    from collections import defaultdict

    # Passo único: agrega por ingrediente sem re-scan da lista.
    by_ing = defaultdict(lambda: {"stores": set(), "prices": 0, "ppk_sum": 0.0, "ppk_count": 0, "min_ppk": float("inf")})
    for p in prices:
        ing = p.get("ingredient_id", "")
        store = p.get("store_id", "")
        ppk = _safe_ppk(p)
        rec = by_ing[ing]
        rec["stores"].add(store)
        rec["prices"] += 1
        if ppk > 0:
            rec["ppk_sum"] += ppk
            rec["ppk_count"] += 1
            rec["min_ppk"] = min(rec["min_ppk"], ppk)

    coverage = []
    for ing, data in by_ing.items():
        coverage.append(
            {
                "ingredient": ing,
                "stores": list(data["stores"]),
                "store_count": len(data["stores"]),
                "prices": data["prices"],
                "min_ppk": data["min_ppk"] if data["ppk_count"] else 0,
                "avg_ppk": data["ppk_sum"] / data["ppk_count"] if data["ppk_count"] else 0,
            }
        )
    return sorted(coverage, key=lambda x: x["ingredient"])


def get_active_promotions():
    """Get currently active promotions."""
    prices = get_latest_prices_cached(valid_only=True, limit=5000)
    return _promotions_from_prices(prices)


def _promotions_from_prices(prices):
    """Promoções ativas a partir de preços já carregados (sem 2ª query)."""
    return [p for p in prices if p.get("is_promotion")]


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
    from datetime import datetime

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
                # Normaliza para aware (assume UTC) — timestamps sem offset
                # (ex.: collected_at naive) causariam TypeError ao subtrair de
                # datetime.now(UTC) mais abaixo.
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
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
# Store Registry Queries
# ============================================================


def get_store_registry_pending_cached() -> list[dict]:
    """Get stores pending review from store_registry."""
    client = get_supabase()
    res = client.table("store_registry").select("*").eq("status", "pending_review").order("created_at", desc=True).execute()
    return res.data or []


def get_store_registry_approved_cached() -> list[dict]:
    """Get approved stores from store_registry, ordered by updated_at."""
    client = get_supabase()
    try:
        res = client.table("store_registry").select("*").eq("status", "approved").order("updated_at", desc=True).execute()
        return res.data or []
    except Exception:
        # Fallback: try ordering by updated_at
        res = client.table("store_registry").select("*").eq("status", "approved").order("created_at", desc=True).execute()
        return res.data or []


def approve_store_registry_cached(entry_id: str) -> bool:
    """Approve a store registry entry and populate store_units."""
    client = get_supabase()
    try:
        now_iso = datetime.now(UTC).isoformat()
        # Fetch entry data before updating
        entry = client.table("store_registry").select("*").eq("id", entry_id).single().execute()
        if not entry.data:
            return False

        client.table("store_registry").update({
            "status": "approved",
            "reviewed_at": now_iso,
            "promoted_at": now_iso,
        }).eq("id", entry_id).execute()

        # Populate store_units if address exists
        if entry.data.get("address"):
            _populate_store_unit(entry.data)

        return True
    except Exception:
        # Fallback without promoted_at column
        try:
            client.table("store_registry").update({
                "status": "approved",
                "reviewed_at": datetime.now(UTC).isoformat(),
            }).eq("id", entry_id).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to approve store registry {entry_id}: {e}")
            return False


def _populate_store_unit(entry: dict):
    """Upsert a store_units row from a store_registry entry."""
    client = get_supabase()
    store_id = entry.get("matched_store_id") or entry.get("id", "")
    unit_data = {
        "store_id": store_id,
        "unit_name": entry.get("name", ""),
        "address": entry.get("address", ""),
        "neighborhood": entry.get("neighborhood", ""),
        "city": entry.get("city", ""),
        "source": "store_registry",
        "confidence": entry.get("address_confidence", 0.5),
        "is_active": True,
    }
    try:
        client.table("store_units").upsert(unit_data, on_conflict="store_id, address").execute()
    except Exception as e:
        logger.debug(f"Failed to populate store_unit: {e}")


def reject_store_registry_cached(entry_id: str) -> bool:
    """Reject a store registry entry."""
    client = get_supabase()
    try:
        client.table("store_registry").update({"status": "rejected"}).eq("id", entry_id).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to reject store registry {entry_id}: {e}")
        return False


def reject_store_registry_bulk_by_prefix_cached(prefix: str) -> int:
    """Reject all pending store_registry entries whose name starts with a prefix
    (ex.: "Cleanup Store" de integration tests). Returns count rejected.
    Processa em lotes de 1000 para respeitar o limite do Supabase."""
    client = get_supabase()
    rejected = 0
    start = 0
    now_iso = datetime.now(UTC).isoformat()
    while True:
        batch = (
            client.table("store_registry")
            .select("id")
            .eq("status", "pending_review")
            .ilike("name", f"{prefix}%")
            .range(start, start + 999)
            .execute()
        )
        ids = [r["id"] for r in (batch.data or [])]
        if not ids:
            break
        try:
            client.table("store_registry").update(
                {"status": "rejected", "reviewed_at": now_iso}
            ).in_("id", ids).execute()
        except Exception as e:
            logger.error(f"Bulk reject failed for {len(ids)} entries: {e}")
            break
        rejected += len(ids)
        if len(ids) < 1000:
            break
        start += 1000
    return rejected


def reject_store_registry_non_food_bulk_cached() -> int:
    """T2.4: rejeita em lote pendentes cujo nome é varejo não-alimentar ou
    título de folheto agregador. Usa o mesmo filtro do collector
    (store_registry._is_food_store_name) para garantir paridade de regra."""
    from services.store_registry import _is_food_store_name

    client = get_supabase()
    now_iso = datetime.now(UTC).isoformat()
    rejected = 0
    start = 0
    while True:
        batch = (
            client.table("store_registry")
            .select("id, name")
            .eq("status", "pending_review")
            .range(start, start + 999)
            .execute()
        )
        rows = batch.data or []
        if not rows:
            break
        bad_ids = [r["id"] for r in rows if not _is_food_store_name(r.get("name", ""))]
        if bad_ids:
            client.table("store_registry").update(
                {"status": "rejected", "reviewed_at": now_iso}
            ).in_("id", bad_ids).execute()
            rejected += len(bad_ids)
        if len(rows) < 1000:
            break
        start += 1000
    return rejected


def merge_store_registry_cached(entry_id: str, target_store_id: str) -> bool:
    """Merge a registry entry into an existing store and populate store_units."""
    client = get_supabase()
    try:
        now_iso = datetime.now(UTC).isoformat()
        # Fetch entry data before updating
        entry = client.table("store_registry").select("*").eq("id", entry_id).single().execute()
        if not entry.data:
            return False

        # Update the registry entry
        client.table("store_registry").update({
            "status": "approved",
            "matched_store_id": target_store_id,
            "reviewed_at": now_iso,
            "promoted_at": now_iso,
        }).eq("id", entry_id).execute()

        # Update the store's address if the registry has one
        if entry.data.get("address"):
            client.table("stores").update({"address": entry.data["address"]}).eq("id", target_store_id).execute()

        # Populate store_units
        unit_data = {
            "store_id": target_store_id,
            "unit_name": entry.data.get("name", ""),
            "address": entry.data.get("address", ""),
            "neighborhood": entry.data.get("neighborhood", ""),
            "city": entry.data.get("city", ""),
            "source": "store_registry",
            "confidence": entry.data.get("address_confidence", 0.5),
            "is_active": True,
        }
        try:
            client.table("store_units").upsert(unit_data, on_conflict="store_id, address").execute()
        except Exception as e:
            logger.debug(f"Failed to upsert store_unit on merge: {e}")

        return True
    except Exception:
        # Fallback without promoted_at column
        try:
            client.table("store_registry").update({
                "status": "approved",
                "matched_store_id": target_store_id,
                "reviewed_at": datetime.now(UTC).isoformat(),
            }).eq("id", entry_id).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to merge store registry {entry_id}: {e}")
            return False


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


def reject_review_queue_bulk_cached(item_ids: list[str]) -> int:
    """T3.1: rejeita múltiplos itens da review_queue em lote."""
    from services.logger import logger
    from services.price_service import reject_review_item

    rejected = 0
    for item_id in item_ids:
        try:
            if reject_review_item(item_id):
                rejected += 1
        except Exception as exc:
            logger.warning("bulk reject failed for %s: %s", item_id, exc)
            continue
    return rejected


def approve_review_queue_bulk_cached(
    item_ids: list[str], ingredient_id: str, brand_override: str = ""
) -> int:
    """T3.1: aprova múltiplos itens da review_queue em lote (mesmo ingrediente)."""
    from services.logger import logger
    from services.price_service import approve_review_item

    approved = 0
    for item_id in item_ids:
        try:
            if approve_review_item(item_id, ingredient_id, brand_override):
                approved += 1
        except Exception as exc:
            logger.warning("bulk approve failed for %s: %s", item_id, exc)
            continue
    return approved


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


@dashboard_data_cache(ttl=300)
def detect_outliers_cached(days: int = 90):
    """Detect price outliers using DB-side RPC (z-score > 2 per ingredient).

    Replaces frontend Python loop with database computation for performance.
    Uses the detect_price_outliers RPC function (migration 013).

    Args:
        days: Lookback window in days (default 90)

    Returns:
        List of dicts with ingredient_id, store_name, raw_product, ppk, zscore
    """
    client = get_supabase()
    try:
        result = client.rpc("detect_price_outliers", {"p_days": days}).execute()
        return result.data or []
    except Exception as e:
        logger.warning(f"Outlier detection RPC failed, falling back to empty: {e}")
        return []


def clear_all_caches():
    """Clear all caches - useful after data mutations.

    Percorre o registro de funções cacheadas (híbrido lru_cache/st.cache_data)
    e, em runtime Streamlit, também limpa o ``st.cache_data`` global — o botão
    "Limpar Cache" (layout.py) e a página Diagnóstico confiam nisso.
    """
    _clear_cached_functions()
    if _streamlit_runtime_active():
        import streamlit as st

        with suppress(Exception):
            st.cache_data.clear()
