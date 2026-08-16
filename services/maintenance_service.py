"""
Maintenance Service - Database cleanup and health checks.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from services.logger import logger
from services.supabase_client import get_service_client

_CLEANUP_TRACK_FILE = Path("data/cleanup_track.json")


def _load_cleanup_track() -> dict[str, Any]:
    if _CLEANUP_TRACK_FILE.exists():
        try:
            return json.loads(_CLEANUP_TRACK_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cleanup_track(data: dict[str, Any]):
    _CLEANUP_TRACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CLEANUP_TRACK_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _check_cleanup_alert(cleanup_name: str, deleted: int) -> None:
    track = _load_cleanup_track()
    today = date.today().isoformat()
    key = f"{cleanup_name}_zero_days"
    if deleted == 0:
        track[key] = track.get(key, 0) + 1
    else:
        track[key] = 0
    track[f"{cleanup_name}_last_run"] = today
    track[f"{cleanup_name}_last_deleted"] = deleted
    _save_cleanup_track(track)
    if track[key] >= 3:
        logger.warning("[ALERT] Cleanup '%s' deleted 0 rows for %d consecutive days", cleanup_name, track[key])


def cleanup_old_prices(retention_days: int = 90) -> dict[str, int]:
    client = get_service_client()
    try:
        result = client.rpc("cleanup_old_prices", {"retention_days": retention_days}).execute()
        deleted = result.data if result.data else 0
        _check_cleanup_alert("cleanup_old_prices", deleted)
        return {"deleted": deleted}
    except Exception:
        _check_cleanup_alert("cleanup_old_prices", 0)
        return {"deleted": 0}


def cleanup_old_logs(retention_days: int = 30) -> dict[str, int]:
    client = get_service_client()
    try:
        result = client.rpc("cleanup_old_logs", {"retention_days": retention_days}).execute()
        deleted = result.data if result.data else 0
        _check_cleanup_alert("cleanup_old_logs", deleted)
        return {"deleted": deleted}
    except Exception:
        _check_cleanup_alert("cleanup_old_logs", 0)
        return {"deleted": 0}


def cleanup_old_flyers_all(retention_days: int = 180) -> dict[str, int]:
    client = get_service_client()
    try:
        result = client.rpc("cleanup_old_flyers_all", {"retention_days": retention_days}).execute()
        deleted = result.data if result.data else 0
        _check_cleanup_alert("cleanup_old_flyers_all", deleted)
        return {"deleted": deleted}
    except Exception:
        _check_cleanup_alert("cleanup_old_flyers_all", 0)
        return {"deleted": 0}


def cleanup_resolved_review_items(retention_days: int = 30) -> dict[str, int]:
    client = get_service_client()
    try:
        result = client.rpc("cleanup_resolved_review_items", {"retention_days": retention_days}).execute()
        deleted = result.data if result.data else 0
        _check_cleanup_alert("cleanup_resolved_review_items", deleted)
        return {"deleted": deleted}
    except Exception:
        _check_cleanup_alert("cleanup_resolved_review_items", 0)
        return {"deleted": 0}


def log_scraper_run(
    store_name: str,
    status: str = "completed",
    items_found: int = 0,
    items_matched: int = 0,
    errors: list[str] | None = None,
    started_at: datetime | None = None,
) -> dict[str, Any]:
    client = get_service_client()
    now = datetime.now(UTC)
    duration = 0
    if started_at:
        duration = int((now - started_at).total_seconds())
    data = {
        "store_name": store_name,
        "status": status,
        "started_at": now.isoformat(),
        "finished_at": now.isoformat(),
        "duration_seconds": duration,
        "items_found": items_found,
        "items_matched": items_matched,
        "errors": errors or [],
    }
    try:
        result = client.table("scraping_logs").insert(data).execute()
        return result.data[0] if result.data else {}
    except Exception:
        return {}


def _retry_delete(client, table: str, name_col: str, prefix: str, max_retries: int = 3) -> int:
    """Deleta registros com retry em erros de rede transitórios (HTTP/2 flaky).

    Supabase REST sobre HTTP/2 derruba conexões silenciosamente (RemoteProtocolError),
    fazendo o delete retornar vazio sem ter apagado nada — o teste de integração
    flakava. Backoff exponencial: 1s, 1.5s, 2.25s."""
    import time

    for attempt in range(1, max_retries + 1):
        try:
            result = client.table(table).delete().ilike(name_col, f"{prefix}%").execute()
            return len(result.data) if result.data else 0
        except Exception as exc:  # noqa: BLE001 - erro de rede precisa de retry
            if attempt >= max_retries:
                logger.debug("cleanup_test_data failed for %s after %d retries: %s", table, attempt, exc)
                return 0
            time.sleep(1.0 * (1.5 ** (attempt - 1)))
    return 0


def cleanup_test_data() -> dict[str, int]:
    client = get_service_client()
    # Coluna de nome real por tabela. IMPORTANTE: o mapeamento é EXPLÍCITO —
    # o padrão antigo `"store_name" if "name" in table else "name"` nunca casava
    # (nenhuma tabela contém "name" no NOME da tabela), então prices,
    # review_queue, scraping_logs e flyers NUNCA eram limpos.
    _TEST_PREFIXES = ("test ", "e2e ", "_test_", "Cleanup Store ")
    _SAFE_TABLES: dict[str, str] = {
        "prices": "store_name",
        "review_queue": "store_name",
        "scraping_logs": "store_name",
        "flyers": "store_name",
        "stores": "name",
        "store_registry": "name",
        "store_units": "unit_name",
    }
    removed: dict[str, int] = {}
    for prefix in _TEST_PREFIXES:
        prefix_norm = prefix.strip()
        for table, name_col in _SAFE_TABLES.items():
            count = _retry_delete(client, table, name_col, prefix_norm)
            if count:
                removed[table] = removed.get(table, 0) + count
    return removed
