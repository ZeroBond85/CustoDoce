"""
Scraper Trend Detector — per-store temporal drift detection (Fase C).

Compara baseline histórico (30d) com janela recente (7d) para CADA loja.
Detecta degradação via z-score aproximado em success_rate, duration e items_matched.
Não usa Isolation Forest (cross-store é statisticalmente fraco com ~25 lojas).

Thresholds:
  trend_score > 0.5 → CRITICAL (alerta imediato)
  trend_score 0.2–0.5 → DEGRADED (observação)
  success_rate últimos 3 runs == 0 → hard fail (CRITICAL, independente de score)
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

from services.logger import logger
from services.supabase_client import get_supabase, safe_execute

# ── Thresholds ──────────────────────────────────────────────
CRITICAL_THRESHOLD = 0.5
DEGRADED_THRESHOLD = 0.2
HARD_FAIL_CONSECUTIVE = 3  # últimos N runs sem sucesso → hard fail
COOLDOWN_HOURS = 4  # horas mínimo entre alertas da mesma loja


def _fetch_store_logs(store_name: str, days: int) -> list[dict[str, Any]]:
    """Busca logs de scraping de uma loja nos últimos N dias."""
    client = get_supabase()
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    rows = safe_execute(
        client.table("scraping_logs")
        .select("status,started_at,duration_seconds,items_found,items_matched")
        .eq("store_name", store_name)
        .gte("started_at", cutoff)
        .order("started_at", desc=True)
    )
    return rows or []


def _success_rate(logs: list[dict[str, Any]]) -> float:
    """Taxa de sucesso: runs com status em {success, completed} / total."""
    if not logs:
        return 0.0
    ok = sum(1 for log in logs if log.get("status") in ("success", "completed"))
    return ok / len(logs)


def _median_duration(logs: list[dict[str, Any]]) -> float:
    """Mediana de duration_seconds."""
    durations = [log.get("duration_seconds", 0) for log in logs if log.get("duration_seconds")]
    if not durations:
        return 0.0
    return float(statistics.median(durations))


def _median_items(logs: list[dict[str, Any]]) -> float:
    """Mediana de items_matched."""
    items = [log.get("items_matched", 0) for log in logs if log.get("items_matched") is not None]
    if not items:
        return 0.0
    return float(statistics.median(items))


def _consecutive_failures(logs: list[dict[str, Any]]) -> int:
    """Contagem de falhas consecutivas do início (logs são desc by started_at)."""
    count = 0
    for log in logs:
        if log.get("status") not in ("success", "completed"):
            count += 1
        else:
            break
    return count


def compute_trend_score(baseline_30d: list[dict[str, Any]], current_7d: list[dict[str, Any]]) -> dict[str, Any]:
    """Computa trend_score comparando janela atual (7d) vs baseline (30d).

    Retorna dict com score, status e breakdown.
    """
    bl_rate = _success_rate(baseline_30d)
    bl_dur = _median_duration(baseline_30d)
    bl_items = _median_items(baseline_30d)

    cur_rate = _success_rate(current_7d)
    cur_dur = _median_duration(current_7d)
    cur_items = _median_items(current_7d)

    # Componente 1: success_rate decay (quanto caiu vs baseline)
    if bl_rate > 0:
        rate_decay = max(0.0, 1.0 - (cur_rate / bl_rate))
    elif cur_rate == 0:
        rate_decay = 0.0
    else:
        rate_decay = 0.3  # baseline 0 + current > 0 → leve penalidade

    # Componente 2: duration increase (quanto aumentou vs baseline)
    dur_increase = max(0.0, (cur_dur / bl_dur) - 1.0) if bl_dur > 0 else 0.0

    # Componente 3: items decrease (quanto caiu vs baseline)
    items_decay = max(0.0, 1.0 - (cur_items / bl_items)) if bl_items > 0 else 0.0 if cur_items == 0 else 0.3

    # Pesos: success_rate (0.5), duration (0.3), items (0.2)
    trend_score = 0.5 * rate_decay + 0.3 * dur_increase + 0.2 * items_decay
    trend_score = min(1.0, max(0.0, trend_score))

    # Status
    if trend_score > CRITICAL_THRESHOLD:
        status = "critical"
    elif trend_score > DEGRADED_THRESHOLD:
        status = "degraded"
    else:
        status = "normal"

    # Hard fail: últimos 3 runs falharam → override para critical
    cons_fails = _consecutive_failures(current_7d)
    if cons_fails >= HARD_FAIL_CONSECUTIVE:
        status = "critical"
        trend_score = max(trend_score, 0.9)

    return {
        "trend_score": round(trend_score, 4),
        "status": status,
        "consecutive_failures": cons_fails,
        "baseline": {
            "success_rate": round(bl_rate, 4),
            "median_duration_s": round(bl_dur, 1),
            "median_items": round(bl_items, 1),
            "sample_size": len(baseline_30d),
        },
        "current": {
            "success_rate": round(cur_rate, 4),
            "median_duration_s": round(cur_dur, 1),
            "median_items": round(cur_items, 1),
            "sample_size": len(current_7d),
        },
    }


def analyze_store(store_name: str) -> dict[str, Any]:
    """Analisa uma loja: busca logs, computa trend, retorna resultado."""
    baseline_30d = _fetch_store_logs(store_name, days=30)
    current_7d = _fetch_store_logs(store_name, days=7)

    result = compute_trend_score(baseline_30d, current_7d)
    result["store_name"] = store_name
    return result


def analyze_all_stores() -> list[dict[str, Any]]:
    """Analisa todas as lojas ativas e retorna lista ordenada por trend_score desc."""
    from services.config_db import get_active_stores

    stores = get_active_stores()
    results = []
    for store in stores:
        name = store.get("name", "")
        if not name:
            continue
        try:
            result = analyze_store(name)
            results.append(result)
        except Exception as e:
            logger.warning("analyze_store failed for %s: %s", name, e)

    results.sort(key=lambda x: x.get("trend_score", 0), reverse=True)
    return results


def should_alert(store_name: str, cooldown_hours: float = COOLDOWN_HOURS) -> bool:
    """Verifica se a loja pode receber alerta (cooldown expirado ou primeiro alerta)."""
    from services.supabase_client import get_service_client

    client = get_service_client()
    row = safe_execute(
        client.table("scraper_alert_state")
        .select("last_alerted_at,active")
        .eq("store_name", store_name)
    )
    if not row:
        return True  # primeiro alerta

    state = row[0]
    last = state.get("last_alerted_at")
    if not last or not state.get("active"):
        return True

    try:
        last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        elapsed = datetime.now(UTC) - last_dt
        return elapsed > timedelta(hours=cooldown_hours)
    except ValueError:
        return True


def update_alert_state(store_name: str, trend_score: float, status: str, active: bool = True) -> None:
    """Persiste estado do alerta para uma loja."""
    from services.supabase_client import get_service_client

    client = get_service_client()
    now = datetime.now(UTC).isoformat()
    data = {
        "store_name": store_name,
        "last_alerted_at": now,
        "last_trend_score": trend_score,
        "last_status": status,
        "active": active,
        "updated_at": now,
    }
    safe_execute(
        client.table("scraper_alert_state")
        .upsert(data, on_conflict="store_name")  # type: ignore[arg-type]
    )
