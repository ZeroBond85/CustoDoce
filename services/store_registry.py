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
    address: str = ""
    neighborhood: str = ""
    phone: str = ""
    address_confidence: float = 0.0
    discovery_source: str = "flyer"
    region: str = ""

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
        "address": entry.address,
        "neighborhood": entry.neighborhood,
        "phone": entry.phone,
        "address_confidence": entry.address_confidence,
        "discovery_source": entry.discovery_source,
        "region": entry.region,
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
                # Conflict: return existing, merge address if incoming has it
                eid = existing.data[0]["id"]
                conflict_data = {k: v for k, v in data.items() if k != "normalized_name"}
                try:
                    existing_row = client.table("store_registry")\
                        .select("address, neighborhood, phone, address_confidence, discovery_source, region")\
                        .eq("id", eid).single().execute().data or {}
                    if not existing_row.get("address") and data.get("address"):
                        conflict_data["address"] = data["address"]
                        conflict_data["neighborhood"] = data.get("neighborhood", "")
                        conflict_data["phone"] = data.get("phone", "")
                        conflict_data["address_confidence"] = data.get("address_confidence", 0)
                        conflict_data["discovery_source"] = data.get("discovery_source", "flyer")
                        conflict_data["region"] = data.get("region", "")
                        client.table("store_registry").update(conflict_data).eq("id", eid).execute()
                except Exception as exc:
                    logger.debug("[store_registry] conflict address merge: %s", exc)
                return StoreRegistryEntry(id=eid, **conflict_data)

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
                address=row.get("address", ""),
                neighborhood=row.get("neighborhood", ""),
                phone=row.get("phone", ""),
                address_confidence=row.get("address_confidence", 0),
                discovery_source=row.get("discovery_source", "flyer"),
                region=row.get("region", ""),
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
        address=row.get("address", ""),
        neighborhood=row.get("neighborhood", ""),
        phone=row.get("phone", ""),
        address_confidence=row.get("address_confidence", 0),
        discovery_source=row.get("discovery_source", "flyer"),
        region=row.get("region", ""),
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


NON_FOOD_KEYWORDS = frozenset({
    "boticário", "boticario", "magazine", "casas bahia", "renner",
    "riachuelo", "marisa", "c&a", "cea", "drogaria", "farmacia",
    "farmácia", "drogasil", "drogão", "drogao", "polishop",
    "fast shop", "electrolux", "lg", "samsung", "sony", "apple",
    "posto", "gasolina", "combustivel", "pet", "petshop",
    "papelaria", "livraria", "academia", "ótica", "otica",
    "oculos", "seguros", "banco", "imobiliária", "imobiliaria",
    "automoveis", "carro", "moto", "cama mesa banho",
    "material de construcao", "construcao", "construção",
    "presentes", "souvenir", "brinquedos", "perfumaria",
    "cosmeticos", "cosméticos", "lavanderia", "telefonia",
    "informatica", "moda", "calçados", "calcados",
})


def _is_food_store_name(name: str) -> bool:
    """Check if a store name is food-related (not a drugstore, electronics, etc.)."""
    if not name:
        return False
    name_lower = name.lower().strip()
    return not any(kw in name_lower for kw in NON_FOOD_KEYWORDS)


def discover_stores_from_flyers() -> int:
    """
    Discover new stores from aggregator flyers.
    Filters non-food stores, checks alias similarity (>=80%), and inserts into store_registry.
    Returns count of new entries inserted.
    """
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("store_registry.discover_stores_from_flyers: no supabase client (%s)", exc)
        return 0

    try:
        flyers = client.table("flyers").select("store_name, region, city, address").execute()
    except Exception as exc:
        logger.warning("discover_stores_from_flyers: query failed: %s", exc)
        return 0

    if not flyers.data:
        return 0

    # Dedup store names (different flyers from same store)
    seen: dict[str, dict] = {}
    for f in flyers.data:
        name = (f.get("store_name") or "").strip()
        if not name:
            continue
        norm = normalize_name(name)
        if not norm:
            continue
        # Filter non-food BEFORE registry
        if not _is_food_store_name(name):
            continue
        # Keep the first occurrence (region + city + address from first flyer)
        if norm not in seen:
            seen[norm] = {"name": name, "normalized_name": norm,
                          "region": f.get("region", ""), "city": f.get("city", ""),
                          "address": f.get("address", "")}

    if not seen:
        return 0

    # Get existing store names (for alias mapping)
    existing_stores: list[dict] = []
    try:
        stores_resp = client.table("stores").select("id, name").eq("is_active", True).execute()
        existing_stores = stores_resp.data or []
    except Exception as exc:
        logger.debug("[store_registry] Could not fetch existing stores: %s", exc)

    # Get existing registry entries (to avoid inserting duplicates)
    existing_registry: list[dict] = []
    try:
        reg_resp = client.table("store_registry") \
            .select("id, name, normalized_name, status, matched_store_id") \
            .in_("status", ["pending_review", "approved"]) \
            .execute()
        existing_registry = reg_resp.data or []
    except Exception as exc:
        logger.debug("[store_registry] Could not fetch existing registry: %s", exc)

    existing_norms: set[str] = {normalize_name(s.get("name", "")) for s in existing_stores}
    existing_norms |= {r.get("normalized_name", "") for r in existing_registry}

    new_count = 0
    for norm, info in seen.items():
        if norm in existing_norms:
            continue

        # Alias mapping: check similarity with existing stores (80% fallback)
        match_score = 0.0
        matched_store_id = None
        for s in existing_stores:
            score = fuzz.token_set_ratio(norm, normalize_name(s.get("name", "")))
            if score >= 80 and score > match_score:
                match_score = score / 100.0
                matched_store_id = s["id"]

        # Also check existing registry
        if not matched_store_id:
            for r in existing_registry:
                score = fuzz.token_set_ratio(norm, r.get("normalized_name", ""))
                if score >= 80 and score > match_score:
                    match_score = score / 100.0
                    matched_store_id = r.get("matched_store_id") or r["id"]

        entry = StoreRegistryEntry(
            name=info["name"],
            normalized_name=norm,
            tier=3,
            type="manual",
            logistics="pickup_local",
            city=info.get("city", ""),
            coverage=info.get("region", info.get("city", "")),
            collection_method="auto",
            source="auto",
            status="pending_review",
            match_score=match_score,
            matched_store_id=matched_store_id,
            address=info.get("address", ""),
            region=info.get("region", ""),
        )
        if info.get("address"):
            entry.address_confidence = 7.0
            entry.discovery_source = "flyer"

        result = upsert_registry_entry(entry)
        if result and result.id:
            new_count += 1
            existing_norms.add(norm)

            # Merge address into existing store if matched
            if result.matched_store_id and result.address:
                merge_store_address_from_registry(result)

    if new_count:
        logger.info("[store_registry] Discovered %d new stores from flyers", new_count)
    return new_count


def merge_store_address_from_registry(entry: StoreRegistryEntry) -> bool:
    """
    Copy address from a registry entry into the matched stores table
    if the store doesn't already have an address.
    """
    if not entry.matched_store_id or not entry.address:
        return False
    try:
        client = get_service_client()
        store = client.table("stores").select("address, id").eq("id", entry.matched_store_id).single().execute()
        if store.data and not store.data.get("address"):
            client.table("stores").update({
                "address": entry.address,
                "neighborhood": entry.neighborhood,
                "phone": entry.phone,
            }).eq("id", entry.matched_store_id).execute()
            logger.info("[store_registry] Address merged into store %s", entry.matched_store_id)
            return True
    except Exception as exc:
        logger.debug("[store_registry] merge_store_address_from_registry failed: %s", exc)
    return False


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
        address=row.get("address", ""),
        neighborhood=row.get("neighborhood", ""),
        phone=row.get("phone", ""),
        address_confidence=row.get("address_confidence", 0),
        discovery_source=row.get("discovery_source", "flyer"),
        region=row.get("region", ""),
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
    "merge_store_address_from_registry",
]
