"""
services/store_registry.py

Centralized store registry with normalization, dedup (RapidFuzz >=92%), and CRUD.
Used by collector for auto-discovery from aggregator flyers.
"""

import logging
import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from services.supabase_client import get_service_client

logger = logging.getLogger(__name__)

# Threshold for considering two stores as duplicates
DEDUP_THRESHOLD = 92


def normalize_name(raw: str) -> str:
    """Normalize store name: upper, alnum + space only."""
    if not raw:
        return ""
    return re.sub(r"[^A-Z0-9 ]", "", raw.upper())


def find_similar_stores(name: str, threshold: int = DEDUP_THRESHOLD, limit: int = 3) -> list[dict]:
    """Find existing stores with name similarity >= threshold using RapidFuzz.
    Returns list of {id, name, similarity} sorted by similarity desc.
    """
    if not name:
        return []
    norm = normalize_name(name)
    if not norm:
        return []

    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("store_registry.find_similar_stores: no supabase client (%s)", exc)
        return []

    stores = client.table("stores").select("id, name").eq("is_active", True).execute().data or []
    results = []
    for s in stores:
        score = fuzz.token_set_ratio(norm, normalize_name(s["name"]))
        if score >= threshold:
            results.append({"id": s["id"], "name": s["name"], "similarity": score / 100.0})

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:limit]


@dataclass
class StoreRegistryEntry:
    """Data class for store registry entries."""
    id: str | None = None
    name: str = ""
    normalized_name: str = ""
    tier: int = 3
    type: str = "manual"
    logistics: str = "pickup_local"
    city: str = ""
    zone: str = ""
    coverage: str = ""
    collection_method: str = "auto"
    source: str = "auto"
    status: str = "pending_review"
    match_score: float = 0.0
    matched_store_id: str | None = None
    config: dict = None

    def __post_init__(self):
        if self.config is None:
            self.config = {}
        if not self.normalized_name:
            self.normalized_name = normalize_name(self.name)


def upsert_registry_entry(entry: StoreRegistryEntry) -> StoreRegistryEntry | None:
    """Insert or update a registry entry. Returns the entry with id populated."""
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("store_registry.upsert_registry_entry: no supabase client (%s)", exc)
        return None

    data = {
        "name": entry.name,
        "normalized_name": entry.normalized_name or normalize_name(entry.name),
        "tier": entry.tier,
        "type": entry.type,
        "logistics": entry.logistics,
        "city": entry.city,
        "zone": entry.zone,
        "coverage": entry.coverage,
        "collection_method": entry.collection_method,
        "source": entry.source,
        "status": entry.status,
        "match_score": entry.match_score,
        "matched_store_id": entry.matched_store_id,
        "config": entry.config,
    }

    try:
        if entry.id:
            res = client.table("store_registry").update(data).eq("id", entry.id).execute()
        else:
            # Check for exact normalized_name conflict (pending/approved)
            existing = client.table("store_registry")\
                .select("id")\
                .eq("normalized_name", data["normalized_name"])\
                .in_("status", ["pending_review", "approved"])\
                .limit(1)\
                .execute()
            if existing.data:
                # Conflict: return existing
                eid = existing.data[0]["id"]
                return StoreRegistryEntry(id=eid, **{k: v for k, v in data.items() if k != "normalized_name"})

            res = client.table("store_registry").insert(data).execute()

        if res.data:
            row = res.data[0]
            return StoreRegistryEntry(
                id=row["id"],
                name=row["name"],
                normalized_name=row["normalized_name"],
                tier=row["tier"],
                type=row["type"],
                logistics=row["logistics"],
                city=row["city"],
                zone=row["zone"],
                coverage=row["coverage"],
                collection_method=row["collection_method"],
                source=row["source"],
                status=row["status"],
                match_score=row["match_score"],
                matched_store_id=row["matched_store_id"],
                config=row["config"] or {},
            )
    except Exception as exc:
        logger.debug("store_registry upsert failed for %s: %s", entry.name, exc)
    return None


def get_pending_review(limit: int = 100) -> list[StoreRegistryEntry]:
    """Get registry entries awaiting review."""
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("store_registry.get_pending_review: no supabase client (%s)", exc)
        return []

    res = client.table("store_registry")\
        .select("*")\
        .eq("status", "pending_review")\
        .order("created_at", desc=False)\
        .limit(limit)\
        .execute()

    return [StoreRegistryEntry(
        id=row["id"],
        name=row["name"],
        normalized_name=row["normalized_name"],
        tier=row["tier"],
        type=row["type"],
        logistics=row["logistics"],
        city=row["city"],
        zone=row["zone"],
        coverage=row["coverage"],
        collection_method=row["collection_method"],
        source=row["source"],
        status=row["status"],
        match_score=row["match_score"],
        matched_store_id=row["matched_store_id"],
        config=row["config"] or {},
    ) for row in res.data or []]


def approve_registry_entry(entry_id: str, ingredient_id: str = "", brand_override: str = "") -> bool:
    """Approve a pending registry entry and attempt merge."""
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("store_registry.approve_registry_entry: no supabase client (%s)", exc)
        return False

    try:
        # Call DB function to merge
        client.rpc("merge_approved_store", {"p_registry_id": entry_id}).execute()
        return True
    except Exception as exc:
        logger.warning("approve_registry_entry merge failed for %s: %s", entry_id, exc)
        return False


def reject_registry_entry(entry_id: str) -> bool:
    """Reject a pending registry entry."""
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("store_registry.reject_registry_entry: no supabase client (%s)", exc)
        return False

    try:
        client.table("store_registry").update({"status": "rejected"}).eq("id", entry_id).execute()
        return True
    except Exception as exc:
        logger.warning("reject_registry_entry failed for %s: %s", entry_id, exc)
        return False


def discover_stores_from_flyers() -> int:
    """Discover new stores from aggregator flyers. Returns count of new entries."""
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("store_registry.discover_stores_from_flyers: no supabase client (%s)", exc)
        return 0

    try:
        client.rpc("discover_stores_from_flyers").execute()
        return 0  # RPC doesn't return count easily
    except Exception as exc:
        logger.warning("discover_stores_from_flyers failed: %s", exc)
        return 0


def get_registry_entry(entry_id: str) -> StoreRegistryEntry | None:
    """Get a single registry entry by id."""
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("store_registry.get_registry_entry: no supabase client (%s)", exc)
        return None

    res = client.table("store_registry").select("*").eq("id", entry_id).single().execute()
    if not res.data:
        return None

    row = res.data
    return StoreRegistryEntry(
        id=row["id"],
        name=row["name"],
        normalized_name=row["normalized_name"],
        tier=row["tier"],
        type=row["type"],
        logistics=row["logistics"],
        city=row["city"],
        zone=row["zone"],
        coverage=row["coverage"],
        collection_method=row["collection_method"],
        source=row["source"],
        status=row["status"],
        match_score=row["match_score"],
        matched_store_id=row["matched_store_id"],
        config=row["config"] or {},
    )


__all__ = [
    "normalize_name",
    "find_similar_stores",
    "DEDUP_THRESHOLD",
    "StoreRegistryEntry",
    "upsert_registry_entry",
    "get_pending_review",
    "approve_registry_entry",
    "reject_registry_entry",
    "discover_stores_from_flyers",
    "get_registry_entry",
]
