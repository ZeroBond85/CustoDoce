# `store_registry` — API

> Última atualização: 2026-07-19 04:56 UTC
> Gerado por AST parsing dos serviços em `services/store_registry.py`.

## Funções Públicas (8)

### approve_registry_entry(entry_id: str, ingredient_id: str, brand_override: str)

Approve a pending registry entry and attempt merge.

### discover_stores_from_flyers()

Discover new stores from aggregator flyers. Returns count of new entries.

### find_similar_stores(name: str, threshold: int, limit: int)

Find existing stores with name similarity >= threshold using RapidFuzz.
Returns list of {id, name, similarity} sorted by similarity desc.

### get_pending_review(limit: int)

Get registry entries awaiting review.

### get_registry_entry(entry_id: str)

Get a single registry entry by id.

### normalize_name(raw: str)

Normalize store name: upper, alnum + space only.

### reject_registry_entry(entry_id: str)

Reject a pending registry entry.

### upsert_registry_entry(entry: StoreRegistryEntry)

Insert or update a registry entry. Returns the entry with id populated.

