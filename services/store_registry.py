"""
services/store_registry.py

Centralized store registry with normalization, dedup (RapidFuzz >=92%), and CRUD.
Used by collector for auto-discovery from aggregator flyers.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta
from typing import Any, cast

from rapidfuzz import fuzz

from services.supabase_client import get_service_client, safe_execute, safe_single_execute

logger = logging.getLogger(__name__)

# Threshold for considering two stores as duplicates
DEDUP_THRESHOLD = 92
# Threshold de alias match para lojas de AGREGAÇÃO (flyers): nomes de flyer são
# ruidosos ("Assaí Atacadista" vs config "Assaí"). 80% deixava 697 lojas reais
# sem matched_store_id → nunca auto-promoviam. 70% é seguro para agregadoras
# (verify via token_set_ratio, não substring). Manuais/explícitos mantêm 80%.
AGGREGATOR_MATCH_THRESHOLD = 70


def normalize_name(raw: str) -> str:
    """Normalize store name: upper, alnum + space only."""
    if not raw:
        return ""
    return re.sub(r"[^A-Z0-9 ]", "", raw.upper())


def _best_store_match(norm: str, stores_pool: list[dict[str, Any]], threshold: int) -> tuple[float, str | None]:
    """Retorna (match_score, matched_store_id) do melhor match por token_set_ratio
    contra o pool de lojas. Pool ampliado (todas lojas, não só is_active) para
    recuperar matches legítimos que antes ficavam sem matched_store_id."""
    best_score = 0.0
    best_id = None
    for s in stores_pool:
        s_id = s.get("id")
        s_name = s.get("name", "")
        if not s_id or not s_name:
            continue
        score = fuzz.token_set_ratio(norm, normalize_name(s_name))
        if score >= threshold and score > best_score:
            best_score = score / 100.0
            best_id = s_id
    return best_score, best_id


def find_similar_stores(name: str, threshold: int = DEDUP_THRESHOLD, limit: int = 3) -> list[dict[str, Any]]:
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

    stores = safe_execute(client.table("stores").select("id, name").eq("is_active", True)) or []
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
    config: dict[str, Any] | None = None
    address: str = ""
    neighborhood: str = ""
    phone: str = ""
    address_confidence: float = 0.0
    discovery_source: str = "flyer"
    region: str = ""

    def __post_init__(self) -> None:
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
            res = safe_execute(client.table("store_registry").update(data).eq("id", entry.id))  # type: ignore[arg-type]
        else:
            # Check for exact normalized_name conflict (pending/approved)
            existing = safe_execute(
                client.table("store_registry")
                .select("id")
                .eq("normalized_name", data["normalized_name"])
                .in_("status", ["pending_review", "approved"])
                .limit(1)
            )
            if existing:
                # Conflict: return existing, merge address if incoming has it
                eid = existing[0]["id"]
                conflict_data = cast("dict[str, Any]", {k: v for k, v in data.items() if k != "normalized_name"})
                try:
                    existing_row = safe_single_execute(
                        client.table("store_registry")
                        .select("address, neighborhood, phone, address_confidence, discovery_source, region, matched_store_id, match_score")
                        .eq("id", eid).single()
                    ) or {}
                    # Backfill matched_store_id/match_score no conflito: antes o
                    # match só era calculado UMA vez no insert (contra pool
                    # is_active=true) e nunca re-avaliado — lojas reais ficavam
                    # sem matched_store_id para sempre, impossibilitando
                    # auto-promoção (697 pendentes em 2026-08-16).
                    if not existing_row.get("matched_store_id") and (data.get("matched_store_id") or entry.matched_store_id):
                        conflict_data["matched_store_id"] = data.get("matched_store_id") or entry.matched_store_id
                        conflict_data["match_score"] = data.get("match_score", 0)
                        safe_execute(client.table("store_registry").update(conflict_data).eq("id", eid))
                    if not existing_row.get("address") and data.get("address"):
                        conflict_data["address"] = data["address"]
                        conflict_data["neighborhood"] = data.get("neighborhood", "")
                        conflict_data["phone"] = data.get("phone", "")
                        conflict_data["address_confidence"] = data.get("address_confidence", 0)
                        conflict_data["discovery_source"] = data.get("discovery_source", "flyer")
                        conflict_data["region"] = data.get("region", "")
                        safe_execute(client.table("store_registry").update(conflict_data).eq("id", eid))
                except Exception as exc:
                    logger.debug("[store_registry] conflict address merge: %s", exc)
                return StoreRegistryEntry(id=eid, **conflict_data)

            res = safe_execute(client.table("store_registry").insert(data))  # type: ignore[arg-type]

        if res:
            row = res[0]
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


def expire_stale_pending(days: int = 30) -> int:
    """Auto-expira entradas pending_review mais antigas que `days` dias.

    Prod tinha 132 pendentes acumuladas (68 aprovadas / 145 rejeitadas ao lado)
    porque nada expirava. Itens expirados ganham status 'expired' (sem CHECK
    constraint no enum) e podem ser re-promovidos manualmente se relevantes.
    Retorna quantas foram expiradas.
    """
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("store_registry.expire_stale_pending: no supabase client (%s)", exc)
        return 0

    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    try:
        res = safe_execute(
            client.table("store_registry")
            .update({"status": "expired", "reviewed_at": datetime.now(UTC).isoformat(), "reviewed_by": "auto-expire"})
            .eq("status", "pending_review")
            .lt("created_at", cutoff)
        )
        count = len(res or [])
        if count:
            logger.info("store_registry: %d pendências >%dd expiradas automaticamente", count, days)
        return count
    except Exception as exc:
        logger.warning("store_registry.expire_stale_pending failed: %s", exc)
        return 0


def get_pending_review(limit: int = 100) -> list[StoreRegistryEntry]:
    """Get registry entries awaiting review."""
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("store_registry.get_pending_review: no supabase client (%s)", exc)
        return []

    res = safe_execute(
        client.table("store_registry")
        .select("*")
        .eq("status", "pending_review")
        .order("created_at", desc=False)
        .limit(limit)
    )

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
    ) for row in res or []]


def approve_registry_entry(entry_id: str, ingredient_id: str = "", brand_override: str = "") -> bool:
    """Approve a pending registry entry and attempt merge."""
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("store_registry.approve_registry_entry: no supabase client (%s)", exc)
        return False

    try:
        # Call DB function to merge
        safe_execute(client.rpc("merge_approved_store", {"p_registry_id": entry_id}))
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
        safe_execute(client.table("store_registry").update({"status": "rejected"}).eq("id", entry_id))
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
    # Varejo não-alimentar visto nos pendentes (2026-08): Havan, Cem,
    # Quero-Quero, Solar, Eudora, Jequiti, Ferreira Costa, TEMU, Decathlon.
    "havan", "cem", "quero-quero", "solar", "eudora", "jequiti",
    "ferreira costa", "temu", "decathlon", "tupperware", "casa e video",
})


def _is_food_store_name(name: str) -> bool:
    """Check if a store name is food-related (not a drugstore, electronics, etc.)."""
    if not name:
        return False
    name_lower = name.lower().strip()
    # Prefixos de teste/integration que poluem o registry (Cleanup Store xxxx,
    # OCR Test Store, _test_...). Filtrados na FONTE — antes entravam como
    # pending_review e a limpeza nunca os removia (ver maintenance_service).
    for prefix in ("cleanup store ", "test ", "e2e ", "_test_", "ocr test "):
        if name_lower.startswith(prefix):
            return False
    # T2.2: nomes de FOLHETO agregador ("Catálogo <loja> em <cidade> | ...")
    # são títulos de flyer com datas, não nomes de loja — poluem o registry
    # (19 pendentes em 2026-08). Filtrados na fonte.
    if name_lower.startswith(("catálogo ", "catalogo ")):
        return False
    return not any(kw in name_lower for kw in NON_FOOD_KEYWORDS)


def _fetch_and_dedup_flyers(client: Any) -> dict[str, dict[str, Any]]:
    """Busca flyers e deduplica por normalized_name, filtrando não-food."""
    try:
        flyers = safe_execute(client.table("flyers").select("store_name, region, city, address"))
    except Exception as exc:
        logger.warning("discover_stores_from_flyers: query failed: %s", exc)
        return {}

    seen: dict[str, dict[str, Any]] = {}
    for f in flyers or []:
        name = (f.get("store_name") or "").strip()
        if not name:
            continue
        norm = normalize_name(name)
        if not norm:
            continue
        if not _is_food_store_name(f.get("store_name") or ""):
            continue
        if norm not in seen:
            seen[norm] = {"name": f.get("store_name", ""), "normalized_name": norm,
                          "region": f.get("region", ""), "city": f.get("city", ""),
                          "address": f.get("address", "")}
    return seen


def _load_existing_data(client: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    """Carrega lojas existentes e registry entries para dedup/match."""
    existing_stores: list[dict[str, Any]] = []
    try:
        existing_stores = safe_execute(client.table("stores").select("id, name"))
    except Exception as exc:
        logger.debug("[store_registry] Could not fetch existing stores: %s", exc)

    existing_registry: list[dict[str, Any]] = []
    try:
        existing_registry = safe_execute(
            client.table("store_registry")
            .select("id, name, normalized_name, status, matched_store_id")
            .in_("status", ["pending_review", "approved"])
        )
    except Exception as exc:
        logger.debug("[store_registry] Could not fetch existing registry: %s", exc)

    existing_norms: set[str] = {normalize_name(s.get("name", "")) for s in existing_stores}
    existing_norms |= {r.get("normalized_name", "") for r in existing_registry}
    return existing_stores, existing_registry, existing_norms


def _find_store_match(norm: str, existing_stores: list[dict[str, Any]], existing_registry: list[dict[str, Any]]) -> tuple[float, str | None]:
    """Encontra melhor match (loja ou registry) via fuzzy token_set_ratio ≥ 70%."""
    match_score = 0.0
    matched_store_id = None
    match_threshold = AGGREGATOR_MATCH_THRESHOLD

    for s in existing_stores:
        score = fuzz.token_set_ratio(norm, normalize_name(s.get("name", "")))
        if score >= match_threshold and score > match_score:
            match_score = score / 100.0
            matched_store_id = s["id"]

    if not matched_store_id:
        for r in existing_registry:
            score = fuzz.token_set_ratio(norm, r.get("normalized_name", ""))
            if score >= match_threshold and score > match_score:
                match_score = score / 100.0
                matched_store_id = r.get("matched_store_id") or r["id"]
    return match_score, matched_store_id


def _build_registry_entry(norm: str, info: dict[str, Any], match_score: float, matched_store_id: str | None) -> StoreRegistryEntry:
    """Constrói StoreRegistryEntry padronizada para descoberta via flyer."""
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
    return entry


def _process_new_store(
    norm: str,
    info: dict[str, Any],
    client: Any,
    existing_norms: set[str],
    existing_stores: list[dict[str, Any]],
    existing_registry: list[dict[str, Any]],
) -> int:
    """Processa uma nova loja candidata: match, upsert, address merge. Retorna 1 se inseriu."""
    if norm in existing_norms:
        return 0

    match_score, matched_store_id = _find_store_match(norm, existing_stores, existing_registry)

    entry = _build_registry_entry(norm, info, match_score, matched_store_id)
    result = upsert_registry_entry(entry)
    if result and result.id:
        if result.matched_store_id and result.address:
            merge_store_address_from_registry(result)
        return 1
    return 0


def discover_stores_from_flyers() -> int:
    """
    Discover new stores from aggregator flyers.
    Filters non-food stores, checks alias similarity (>=70%), and inserts into store_registry.
    Returns count of new entries inserted.
    """
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("store_registry.discover_stores_from_flyers: no supabase client (%s)", exc)
        return 0

    # Housekeeping: pendências >30d viram 'expired' antes de avaliar novas
    expire_stale_pending(days=30)

    seen = _fetch_and_dedup_flyers(client)
    if not seen:
        return 0

    existing_stores, existing_registry, existing_norms = _load_existing_data(client)
    if not seen:
        return 0

    new_count = 0
    for norm, info in seen.items():
        new_count += _process_new_store(
            norm, info, client, existing_norms,
            existing_stores, existing_registry
        )

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
        store = safe_single_execute(client.table("stores").select("address, id").eq("id", entry.matched_store_id).single())
        if store and not store.get("address"):
            safe_execute(client.table("stores").update({
                "address": entry.address,
                "neighborhood": entry.neighborhood,
                "phone": entry.phone,
            }).eq("id", entry.matched_store_id))
            logger.info("[store_registry] Address merged into store %s", entry.matched_store_id)
            return True
    except Exception as exc:
        logger.debug("[store_registry] merge_store_address_from_registry failed: %s", exc)
    return False




def auto_promote_discovered_stores(min_matched_products: int = 2) -> int:
    """
    Auto-promote stores from pending_review to approved if they have
    >= min_matched_products confirmed ingredient matches.

    Only promotes stores that already have a matched_store_id (linked to existing store).
    New stores without matched_store_id require manual review with scraper config.
    """
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("store_registry.auto_promote: no supabase client (%s)", exc)
        return 0

    try:
        # Get pending stores that already have a matched_store_id
        pending = safe_execute(
            client.table("store_registry")
            .select("id, name, matched_store_id, source, discovery_source, tier")
            .eq("status", "pending_review")
        )
        if not pending:
            return 0

        promoted = 0
        for entry in pending:
            store_name = entry["name"]
            matched_id = entry.get("matched_store_id")
            entry_id = entry["id"]

            # Fix 4.4: agregadoras (source/discovery auto) sem matched_store_id
            # podem ser promovidas se já produzem preços — são lojas reais
            # descobertas de flyers, dispensam scraper config (tier 3).
            # Antes, `if not matched_id: continue` descartava todas as 697 sem
            # match, deixando a fila crescer indefinidamente.
            if not matched_id:
                src = (entry.get("source") or "").lower()
                disc = (entry.get("discovery_source") or "").lower()
                is_aggregator = src in ("auto", "flyer", "portal") or disc in ("flyer", "auto")
                if not is_aggregator:
                    continue
                # Sem matched_store_id: conta ingredientes por store_name direto
                prices = safe_execute(
                    client.table("prices")
                    .select("ingredient_id")
                    .eq("store_name", store_name)
                )
                matched_count = len({p.get("ingredient_id") for p in prices if p.get("ingredient_id")})
                if matched_count < min_matched_products:
                    continue
                now_iso = datetime.now(UTC).isoformat()
                safe_execute(client.table("store_registry").update({
                    "status": "approved",
                    "promoted_at": now_iso,
                    "reviewed_at": now_iso,
                }).eq("id", entry_id))
                logger.info("[store_registry] Auto-promoted aggregator %s (%d products)", store_name, matched_count)
                promoted += 1
                continue

            # Count distinct ingredients matched in prices for this store.
            # Fix 4.5: o nome do preço pode diferir do registry (ex.: price usa
            # nome do scraper config). Conta por matched_store_id quando
            # disponível — antes contava só por store_name == registry, que
            # quase nunca batia (matched_count=0 → nenhuma promoção).
            prices = safe_execute(
                client.table("prices")
                .select("ingredient_id")
                .eq("store_id", matched_id)
            )
            matched_count = len({p.get("ingredient_id") for p in prices if p.get("ingredient_id")})
            if matched_count < min_matched_products:
                continue

            now_iso = datetime.now(UTC).isoformat()
            safe_execute(client.table("store_registry").update({
                "status": "approved",
                "promoted_at": now_iso,
                "reviewed_at": now_iso,
            }).eq("id", entry_id))
            logger.info("[store_registry] Auto-promoted %s (matched to store %s, %d products)",
                        store_name, matched_id, matched_count)
            promoted += 1

        if promoted:
            logger.info("[store_registry] Auto-promoted %d stores", promoted)
        return promoted

    except Exception as exc:
        logger.warning("store_registry.auto_promote failed: %s", exc)
        return 0


def get_registry_entry(entry_id: str) -> StoreRegistryEntry | None:
    """Get a single registry entry by id."""
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("store_registry.get_registry_entry: no supabase client (%s)", exc)
        return None

    row = safe_single_execute(client.table("store_registry").select("*").eq("id", entry_id).single())
    if not row:
        return None
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
