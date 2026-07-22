# `store_registry` — API

> Última atualização: 2026-07-22 22:25 UTC
> Gerado por AST parsing dos serviços em `services/store_registry.py`.

## Funções Públicas (9)

### approve_registry_entry(entry_id: str, ingredient_id: str, brand_override: str)

Approve a pending registry entry and attempt merge.

### discover_stores_from_flyers()

Discover new stores from aggregator flyers.
Filters non-food stores, checks alias similarity (>=80%), and inserts into store_registry.
Returns count of new entries inserted.

### find_similar_stores(name: str, threshold: int, limit: int)

Find existing stores with name similarity >= threshold using RapidFuzz.
Returns list of {id, name, similarity} sorted by similarity desc.

### get_pending_review(limit: int)

Get registry entries awaiting review.

### get_registry_entry(entry_id: str)

Get a single registry entry by id.

### merge_store_address_from_registry(entry: StoreRegistryEntry)

Copy address from a registry entry into the matched stores table
if the store doesn't already have an address.

### normalize_name(raw: str)

Normalize store name: upper, alnum + space only.

### reject_registry_entry(entry_id: str)

Reject a pending registry entry.

### upsert_registry_entry(entry: StoreRegistryEntry)

Insert or update a registry entry. Returns the entry with id populated.

