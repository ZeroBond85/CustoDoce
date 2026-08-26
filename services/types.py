"""
Core type definitions for CustoDoce.
Ensures consistency across services, parsers, and the database.
"""

from __future__ import annotations

from typing import Any, NotRequired, Protocol, TypedDict, runtime_checkable


# --- Base Entities ---


class Ingredient(TypedDict):
    id: str
    canonical_name: str
    category: str
    aliases: list[str]
    search_terms: list[str]
    unit_target: str
    active: bool
    created_at: NotRequired[str]
    updated_at: NotRequired[str]


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
    url_pattern: NotRequired[str]
    base_url: NotRequired[str]
    api_endpoint: NotRequired[str]
    search_url: NotRequired[str]
    selectors: NotRequired[dict[str, Any]]
    publish_day: NotRequired[str]
    visit_frequency: NotRequired[str]
    contact: NotRequired[str]
    created_at: NotRequired[str]
    updated_at: NotRequired[str]


# Input types (para upsert — sem campos gerados pelo DB)
class StoreInput(TypedDict):
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
    url_pattern: NotRequired[str]
    base_url: NotRequired[str]
    api_endpoint: NotRequired[str]
    search_url: NotRequired[str]
    selectors: NotRequired[dict[str, Any]]
    publish_day: NotRequired[str]
    visit_frequency: NotRequired[str]
    contact: NotRequired[str]


class Flyer(TypedDict):
    id: str
    store_name: str
    region: str
    city: str
    address: NotRequired[str]
    flyer_title: str
    flyer_date_start: NotRequired[str]
    flyer_date_end: NotRequired[str]
    image_url: str
    image_hash: str
    image_type: str
    image_width: NotRequired[int]
    image_height: NotRequired[int]
    ocr_status: str
    ocr_text: NotRequired[str]
    ocr_confidence: NotRequired[float]
    products_extracted: int
    source: str
    valid_from: NotRequired[str]
    valid_until: NotRequired[str]
    collected_at: str
    processed_at: NotRequired[str]


# --- Price & History ---


class PriceNormalized(TypedDict):
    price_per_kg: float
    price_per_un: float
    total_kg: float
    qty: float
    unit_kg: float


class PriceEntry(TypedDict):
    id: NotRequired[str]
    ingredient_id: str
    store_id: str
    source: str
    store_name: str
    raw_product: str
    raw_price: float
    raw_unit: str
    collected_at: str
    valid_from: str
    valid_until: str
    validity_raw: str
    collected_weekday: str
    is_promotion: bool
    tier: int
    confidence: float
    normalized: NotRequired[PriceNormalized]
    city: str
    logistics: str
    brand: str


# --- Review Queue ---


class ReviewItem(TypedDict):
    id: NotRequired[str]
    raw_product: str
    raw_price: NotRequired[float]
    raw_unit: str
    store_name: str
    source: str
    confidence: float
    suggestions: list[str]
    validity_raw: str
    status: str
    resolved_ingredient: NotRequired[str]
    brand: str
    image_url: str
    source_url: str
    match_reason: str
    match_type: str
    top3: list[dict[str, Any]]
    collected_at: NotRequired[str]
    reviewed_at: NotRequired[str]


class AlertRule(TypedDict):
    id: str
    trigger: str
    channel: str
    threshold: float
    enabled: bool
    ingredient_id: NotRequired[str]
    store_id: NotRequired[str]


class AlertRecipient(TypedDict):
    id: str
    channel: str
    target: str
    active: bool


class ScrapingLog(TypedDict):
    id: str
    store_name: str
    tier: int
    status: str
    started_at: str
    completed_at: NotRequired[str]
    items_found: int
    items_matched: int
    errors: list[str]
    error_class: NotRequired[str]


# --- Protocols ---


@runtime_checkable
class PriceRepository(Protocol):
    def get_latest_prices(self, valid_only: bool, limit: int) -> list[PriceEntry]: ...
    def upsert_price(self, entry: PriceEntry) -> None: ...
    def batch_upsert_prices(self, entries: list[PriceEntry]) -> None: ...


@runtime_checkable
class FlyerRepository(Protocol):
    def get_flyers_by_store(self, store_name: str) -> list[Flyer]: ...
    def upsert_flyer(self, flyer: Flyer) -> None: ...


@runtime_checkable
class ScraperProtocol(Protocol):
    def run(self, ingredients: list[Ingredient] | None = None) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...
