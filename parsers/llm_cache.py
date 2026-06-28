"""
Cache SQLite local para decisões do LLM Classifier.

Objetivo (RFC Recurso 3): Reduzir chamadas redundantes à API Groq.
- TTL: 30 dias (configurável por env LLM_CACHE_TTL_DAYS).
- Hash key: SHA-256(product_name + brand) para evitar repassar dados confidenciais.
- Persiste em `data/llm_cache.db`.
- Função de cleanup `cleanup_ttl()` deve ser chamada na rotina de housekeeping.
"""

import os
import sqlite3
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from services.logger import logger

_CACHE_DIR = Path(os.environ.get("LLM_CACHE_DIR", "data"))
_CACHE_DB = _CACHE_DIR / "llm_cache.db"
_CACHE_TTL_DAYS = int(os.environ.get("LLM_CACHE_TTL_DAYS", "30"))


def _ensure_dir() -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(str(_CACHE_DB))
    conn.row_factory = sqlite3.Row
    return conn


def _init_schema() -> None:
    """Garante que a tabela de cache existe (idempotente)."""
    try:
        with _get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    hash_key TEXT PRIMARY KEY,
                    product_name TEXT NOT NULL,
                    brand TEXT NOT NULL DEFAULT '',
                    decision TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    ttl_days INTEGER NOT NULL DEFAULT 30
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_created ON cache(created_at)")
            conn.commit()
    except Exception as e:
        logger.debug("init_cache_schema_failed", error=str(e))


def _hash_key(product_name: str, brand: str = "") -> str:
    payload = f"{(product_name or '').strip().lower()}|{(brand or '').strip().lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_cache(product_name: str, brand: str = "") -> dict | None:
    """
    Recupera decisão cacheada no SQLite local.
    Returns:
        dict com a decisão se TTL ainda válido, None caso contrário.
    """
    _init_schema()
    if not product_name:
        return None
    try:
        h = _hash_key(product_name, brand)
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT decision, created_at, ttl_days FROM cache WHERE hash_key = ?",
                (h,),
            ).fetchone()
            if not row:
                return None
            created = datetime.fromisoformat(row["created_at"])
            ttl = row["ttl_days"] or _CACHE_TTL_DAYS
            if datetime.now() - created > timedelta(days=ttl):
                # Expirado - remove
                conn.execute("DELETE FROM cache WHERE hash_key = ?", (h,))
                conn.commit()
                return None
            return json.loads(row["decision"])
    except Exception as e:
        logger.debug("llm_cache_get_failed", error=str(e))
        return None


def set_cache(product_name: str, brand: str, decision: dict, ttl_days: int | None = None) -> None:
    """
    Salva decisão no cache local.
    """
    _init_schema()
    if not product_name or decision is None:
        return
    try:
        h = _hash_key(product_name, brand)
        ttl = ttl_days if ttl_days is not None else _CACHE_TTL_DAYS
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache (hash_key, product_name, brand, decision, created_at, ttl_days)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    h,
                    product_name,
                    brand or "",
                    json.dumps(decision, ensure_ascii=False),
                    datetime.now().isoformat(),
                    ttl,
                ),
            )
            conn.commit()
    except Exception as e:
        logger.debug("llm_cache_set_failed", error=str(e))


def cleanup_ttl(ttl_days: int | None = None) -> int:
    """
    Remove entradas com TTL expirado.
    Returns:
        número de linhas removidas.
    """
    _init_schema()
    try:
        with _get_conn() as conn:
            datetime.now().isoformat()
            expiry_ts = (datetime.now() - timedelta(days=ttl_days or _CACHE_TTL_DAYS)).isoformat()
            cur = conn.execute(
                "DELETE FROM cache WHERE datetime(created_at) < datetime(?)",
                (expiry_ts,),
            )
            conn.commit()
            return cur.rowcount
    except Exception as e:
        logger.debug("llm_cache_cleanup_failed", error=str(e))
        return 0


def cache_stats() -> dict:
    """
    Estatísticas do cache local para diagnóstico.
    """
    _init_schema()
    try:
        with _get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM cache").fetchone()["c"]
            expiry_ts = (datetime.now() - timedelta(days=_CACHE_TTL_DAYS)).isoformat()
            expired = conn.execute(
                "SELECT COUNT(*) as c FROM cache WHERE datetime(created_at) < datetime(?)",
                (expiry_ts,),
            ).fetchone()["c"]
            return {"total": total, "expired": expired, "ttl_days": _CACHE_TTL_DAYS}
    except Exception as e:
        logger.debug("llm_cache_stats_failed", error=str(e))
        return {"total": 0, "expired": 0, "ttl_days": _CACHE_TTL_DAYS, "error": str(e)}
