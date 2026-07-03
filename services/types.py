"""
Core type definitions for CustoDoce.
Ensures consistency across services, parsers, and the database.
"""

from __future__ import annotations

from typing import TypedDict, Any, Protocol, runtime_checkable

# --- Base Entities ---


class Ingredient(TypedDict):
    id: str
    canonical_name: str
    category: str
    aliases: list[str]
    search_terms: list[str]
    unit_target: str
    active: bool
    created_at: str | None
    updated_at: str | None


class Store(TypedDict):
    id: str
    name: str
    tier: int
    type: str
    logistics: str
    city: str
    zone: str
    coverage: str
    collection_method: str
    is_active: bool
    priority: int
    scraper: str
    url_pattern: str | None
    base_url: str | None
    api_endpoint: str | None
    search_url: str | None
    selectors: dict[str, Any]
    publish_day: str | None
    visit_frequency: str | None
    contact: str | None
    created_at: str | None
    updated_at: str | None


# --- Price & History ---


class PriceNormalized(TypedDict):
    price_per_kg: float
    price_per_un: float
    total_kg: float
    qty: float


class PriceEntry(TypedDict):
    id: str | None
    ingredient_id: str
    store_id: str
    source: str
    store_name: str
    raw_product: str
    raw_price: float
    raw_unit: str
    collected_at: str  # ISO date
    valid_from: str  # ISO date
    valid_until: str  # ISO date
    validity_raw: str
    collected_weekday: str
    is_promotion: bool
    tier: int
    confidence: float
    normalized: PriceNormalized | None
    city: str
    logistics: str
    brand: str


# --- Review Queue ---


class ReviewItem(TypedDict):
    id: str | None
    raw_product: str
    raw_price: float | None
    raw_unit: str
    store_name: str
    source: str
    confidence: float
    suggestions: list[str]
    validity_raw: str
    status: str  # 'pending', 'approved', 'rejected'
    resolved_ingredient: str | None
    brand: str
    image_url: str
    source_url: str
    match_reason: str
    match_type: str
    top3: list[dict[str, Any]]
    collected_at: str | None
    reviewed_at: str | None


# --- Protocols ---


@runtime_checkable
class Scraper(Protocol):
    def __init__(self, store: Store) -> None: ...
    def __enter__(self) -> Scraper: ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...
    def run(self, ingredients: list[Ingredient] | None = None) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...
