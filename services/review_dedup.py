"""
Review Dedup — semantic deduplication for review_queue (Fase C).

Usa RapidFuzz token_sort_ratio (não embeddings e5 — que são query→passage, não product→product).
Threshold default: 90 (calibrado para near-identical strings).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from rapidfuzz import fuzz

from services.supabase_client import get_supabase, safe_execute

SEMANTIC_DEDUP_THRESHOLD = 90.0
DEDUP_LOOKBACK_DAYS = 7


def _normalize(text: str) -> str:
    """Normaliza texto para comparação: lowercase, strip, sem acentos."""
    import unicodedata

    text = text.lower().strip()
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def is_semantic_duplicate(
    new_product: str,
    existing_products: list[str],
    threshold: float = SEMANTIC_DEDUP_THRESHOLD,
) -> dict[str, Any] | None:
    """Retorna top-1 similar se score >= threshold, senão None.

    Args:
        new_product: Nome do novo produto a inserir.
        existing_products: Lista de nomes de produtos já na fila.
        threshold: Score mínimo RapidFuzz (0–100) para considerar duplicata.
    """
    norm_new = _normalize(new_product)
    if not norm_new:
        return None

    best_score = 0.0
    best_existing: str | None = None

    for existing in existing_products:
        norm_existing = _normalize(existing)
        if not norm_existing:
            continue
        score = fuzz.token_sort_ratio(norm_new, norm_existing)
        if score > best_score:
            best_score = score
            best_existing = existing

    if best_score >= threshold and best_existing is not None:
        return {"existing_product": best_existing, "score": round(best_score, 1)}
    return None


def find_pending_duplicates(
    raw_product: str,
    store_name: str,
    threshold: float = SEMANTIC_DEDUP_THRESHOLD,
    lookback_days: int = DEDUP_LOOKBACK_DAYS,
) -> dict[str, Any] | None:
    """Busca pending items na review_queue e verifica duplicata semântica."""
    client = get_supabase()
    cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()

    pending = safe_execute(
        client.table("review_queue")
        .select("raw_product,confidence")
        .eq("store_name", store_name)
        .eq("status", "pending")
        .gte("collected_at", cutoff)
        .limit(100)
    )

    if not pending:
        return None

    existing_texts = [p.get("raw_product", "") for p in pending if p.get("raw_product")]
    return is_semantic_duplicate(raw_product, existing_texts, threshold)
