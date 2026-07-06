"""Central mock data repository — all table-level mocks in one place.

Each mock dict/record has readable placeholder IDs (not real UUIDs)
so tests stay readable. Fields follow the exact schema from
config/schema_manifest.json (columns, types, not_null, defaults).
"""

from __future__ import annotations

import copy
from typing import Any

# ─── Ingredients ────────────────────────────────────────────────────────────

MOCK_INGREDIENTS: list[dict[str, Any]] = [
    {
        "id": "ing-001",
        "canonical_name": "Leite Condensado",
        "category": "Laticínios",
        "aliases": ["Leite Condensado", "Condensado", "Leite Moça"],
        "unit_target": "kg",
        "active": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "brands": ["Moça", "Piracanjuba", "Italac", "Itambé"],
        "search_terms": ["leite condensado", "leite moça", "condensado"],
    },
    {
        "id": "ing-002",
        "canonical_name": "Creme de Leite",
        "category": "Laticínios",
        "aliases": ["Creme de Leite", "Creme"],
        "unit_target": "kg",
        "active": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "brands": ["Nestlé", "Piracanjuba", "Itambé"],
        "search_terms": ["creme de leite", "creme"],
    },
    {
        "id": "ing-003",
        "canonical_name": "Chocolate em Pó 50%",
        "category": "Chocolates",
        "aliases": ["Chocolate 50%", "Chocolate em Pó"],
        "unit_target": "kg",
        "active": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "brands": ["Nestlé", "Melken"],
        "search_terms": ["chocolate 50%", "chocolate em pó"],
    },
]

# ─── Stores ─────────────────────────────────────────────────────────────────

MOCK_STORES: list[dict[str, Any]] = [
    {
        "id": "store-001",
        "name": "Assaí Atacadista",
        "tier": 1,
        "type": "atacadista",
        "logistics": "pickup_local",
        "city": "Santos",
        "zone": "Baixada Santista",
        "coverage": "regional",
        "collection_method": "pdf",
        "is_active": True,
        "priority": 1,
        "config": {},
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "scraper": "base_flyer",
        "url_pattern": "https://example.com/assi/{date}",
        "base_url": "https://example.com",
        "api_endpoint": None,
        "search_url": None,
        "selectors": {},
        "publish_day": "quarta-feira",
        "visit_frequency": "weekly",
        "contact": None,
    },
    {
        "id": "store-002",
        "name": "Mercado Livre",
        "tier": 2,
        "type": "ecommerce",
        "logistics": "delivery",
        "city": "São Paulo",
        "zone": "SP Capital",
        "coverage": "nacional",
        "collection_method": "api",
        "is_active": True,
        "priority": 5,
        "config": {},
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "scraper": None,
        "url_pattern": None,
        "base_url": "https://mercadolivre.com.br",
        "api_endpoint": "https://api.mercadolibre.com",
        "search_url": "https://lista.mercadolivre.com.br/{query}",
        "selectors": {},
        "publish_day": None,
        "visit_frequency": "daily",
        "contact": None,
    },
]

# ─── Prices (prices table — includes price_per_kg) ──────────────────────────

MOCK_PRICES: list[dict[str, Any]] = [
    {
        "id": "price-001",
        "ingredient_id": "ing-001",
        "store_id": "store-001",
        "source": "automated",
        "store_name": "Assaí Atacadista",
        "raw_product": "Leite Condensado Moça 395g",
        "raw_price": "10.50",
        "raw_unit": "395g",
        "collected_at": "2026-06-28T10:00:00Z",
        "valid_from": "2026-06-28",
        "valid_until": "2026-07-05",
        "validity_raw": "semanal",
        "collected_weekday": "sábado",
        "is_promotion": False,
        "tier": 1,
        "confidence": 1.0,
        "normalized": {
            "qty": 1,
            "unit_kg": 0.395,
            "total_kg": 0.395,
            "price_per_kg": 26.58,
            "price_per_un": 10.50,
        },
        "city": "Santos",
        "logistics": "pickup_local",
        "created_at": "2026-06-28T10:00:00Z",
        "brand": "Moça",
        "price_per_kg": 26.58,
    },
    {
        "id": "price-002",
        "ingredient_id": "ing-001",
        "store_id": "store-002",
        "source": "automated",
        "store_name": "Mercado Livre",
        "raw_product": "Leite Condensado Piracanjuba 395g",
        "raw_price": "12.90",
        "raw_unit": "395g",
        "collected_at": "2026-06-28T11:00:00Z",
        "valid_from": "2026-06-28",
        "valid_until": "2026-07-05",
        "validity_raw": "semanal",
        "collected_weekday": "sábado",
        "is_promotion": False,
        "tier": 2,
        "confidence": 1.0,
        "normalized": {
            "qty": 1,
            "unit_kg": 0.395,
            "total_kg": 0.395,
            "price_per_kg": 32.66,
            "price_per_un": 12.90,
        },
        "city": "São Paulo",
        "logistics": "delivery",
        "created_at": "2026-06-28T11:00:00Z",
        "brand": "Piracanjuba",
        "price_per_kg": 32.66,
    },
    {
        "id": "price-003",
        "ingredient_id": "ing-002",
        "store_id": "store-001",
        "source": "automated",
        "store_name": "Assaí Atacadista",
        "raw_product": "Creme de Leite Nestlé 200g",
        "raw_price": "8.90",
        "raw_unit": "200g",
        "collected_at": "2026-06-28T10:00:00Z",
        "valid_from": "2026-06-28",
        "valid_until": "2026-07-05",
        "validity_raw": "semanal",
        "collected_weekday": "sábado",
        "is_promotion": True,
        "tier": 1,
        "confidence": 1.0,
        "normalized": {
            "qty": 1,
            "unit_kg": 0.2,
            "total_kg": 0.2,
            "price_per_kg": 44.50,
            "price_per_un": 8.90,
        },
        "city": "Santos",
        "logistics": "pickup_local",
        "created_at": "2026-06-28T10:00:00Z",
        "brand": "Nestlé",
        "price_per_kg": 44.50,
    },
]

# ─── Latest prices (v_latest_prices view — subset of prices columns) ────────

MOCK_LATEST_PRICES: list[dict[str, Any]] = [
    {
        "id": "price-001",
        "ingredient_id": "ing-001",
        "store_id": "store-001",
        "store_name": "Assaí Atacadista",
        "raw_product": "Leite Condensado Moça 395g",
        "raw_price": "10.50",
        "raw_unit": "395g",
        "normalized": {
            "qty": 1,
            "unit_kg": 0.395,
            "total_kg": 0.395,
            "price_per_kg": 26.58,
            "price_per_un": 10.50,
        },
        "price_per_kg": 26.58,
        "collected_at": "2026-06-28T10:00:00Z",
        "valid_from": "2026-06-28",
        "valid_until": "2026-07-05",
        "is_promotion": False,
        "tier": 1,
        "confidence": 1.0,
        "city": "Santos",
        "logistics": "pickup_local",
        "brand": "Moça",
    },
    {
        "id": "price-003",
        "ingredient_id": "ing-002",
        "store_id": "store-001",
        "store_name": "Assaí Atacadista",
        "raw_product": "Creme de Leite Nestlé 200g",
        "raw_price": "8.90",
        "raw_unit": "200g",
        "normalized": {
            "qty": 1,
            "unit_kg": 0.2,
            "total_kg": 0.2,
            "price_per_kg": 44.50,
            "price_per_un": 8.90,
        },
        "price_per_kg": 44.50,
        "collected_at": "2026-06-28T10:00:00Z",
        "valid_from": "2026-06-28",
        "valid_until": "2026-07-05",
        "is_promotion": True,
        "tier": 1,
        "confidence": 1.0,
        "city": "Santos",
        "logistics": "pickup_local",
        "brand": "Nestlé",
    },
]

# ─── Price History ──────────────────────────────────────────────────────────

MOCK_PRICE_HISTORY: list[dict[str, Any]] = [
    {
        "id": "hist-001",
        "price_id": "price-001",
        "ingredient_id": "ing-001",
        "store_id": "store-001",
        "store_name": "Assaí Atacadista",
        "raw_product": "Leite Condensado Moça 395g",
        "raw_price": "10.50",
        "raw_unit": "395g",
        "normalized": {
            "qty": 1,
            "unit_kg": 0.395,
            "total_kg": 0.395,
            "price_per_kg": 26.58,
            "price_per_un": 10.50,
        },
        "valid_from": "2026-06-21",
        "valid_until": "2026-06-28",
        "validity_raw": "semanal",
        "collected_weekday": "sábado",
        "is_promotion": False,
        "collected_at": "2026-06-21T10:00:00Z",
        "brand": "Moça",
        "price_per_kg": 26.58,
    },
]

# ─── Review Queue ───────────────────────────────────────────────────────────

MOCK_REVIEW_QUEUE: list[dict[str, Any]] = [
    {
        "id": "review-001",
        "raw_product": "Leite Cond Piracanjuba 395g",
        "raw_price": "11.50",
        "raw_unit": "1kg",
        "store_name": "Assaí Atacadista",
        "source": "automated",
        "confidence": 0.65,
        "suggestions": [
            {"ingredient": "Leite Condensado", "confidence": 0.65},
            {"ingredient": "Creme de Leite", "confidence": 0.30},
        ],
        "validity_raw": "semanal",
        "status": "pending",
        "resolved_ingredient": None,
        "collected_at": "2026-06-28T10:00:00Z",
        "reviewed_at": None,
        "brand": "Piracanjuba",
        "image_url": "",
        "source_url": "",
        "match_reason": "fuzzy >55%",
        "match_type": "proximo_nome",
        "top3": [
            {"ingredient": "Leite Condensado", "confidence": 0.65},
            {"ingredient": "Creme de Leite", "confidence": 0.30},
            {"ingredient": "Leite em Pó", "confidence": 0.05},
        ],
    },
]

# ─── Scraping Logs ──────────────────────────────────────────────────────────

MOCK_SCRAPING_LOGS: list[dict[str, Any]] = [
    {
        "id": "log-001",
        "store_name": "Assaí Atacadista",
        "status": "success",
        "started_at": "2026-06-28T10:00:00Z",
        "finished_at": "2026-06-28T10:02:30Z",
        "items_found": 45,
        "items_matched": 38,
        "errors": [],
        "duration_seconds": 150,
    },
    {
        "id": "log-002",
        "store_name": "Mercado Livre",
        "status": "error",
        "started_at": "2026-06-28T11:00:00Z",
        "finished_at": "2026-06-28T11:00:05Z",
        "items_found": 0,
        "items_matched": 0,
        "errors": [{"type": "timeout", "msg": "Connection timed out"}],
        "duration_seconds": 5,
    },
]

# ─── Scraper Health Log ─────────────────────────────────────────────────────

MOCK_SCRAPER_HEALTH: list[dict[str, Any]] = [
    {
        "id": "health-001",
        "scraper_name": "base_flyer",
        "event_type": "success",
        "error_class": None,
        "reason": "Coleta concluída com 38 matches",
        "failures_count": 0,
        "is_active": True,
        "attempted_by": "auto",
        "created_at": "2026-06-28T10:02:30Z",
    },
    {
        "id": "health-002",
        "scraper_name": "vtex_api",
        "event_type": "failure",
        "error_class": "TimeoutError",
        "reason": "Connection timed out after 30s",
        "failures_count": 3,
        "is_active": False,
        "attempted_by": "auto",
        "created_at": "2026-06-28T11:00:05Z",
    },
]

# ─── Schedules ──────────────────────────────────────────────────────────────

MOCK_SCHEDULES: list[dict[str, Any]] = [
    {
        "id": "sched-001",
        "name": "Coleta Diária",
        "cron_expression": "0 6 * * *",
        "timezone": "America/Sao_Paulo",
        "payload": {"stores": ["store-001", "store-002"]},
        "enabled": True,
        "last_run": "2026-06-28T06:00:00Z",
        "next_run": "2026-06-29T06:00:00Z",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    },
]

# ─── Feature Flags ──────────────────────────────────────────────────────────

MOCK_FEATURE_FLAGS: list[dict[str, Any]] = [
    {
        "key": "scraper_vtex_enabled",
        "enabled": True,
        "description": "Habilita scraper de lojas VTEX",
        "updated_at": "2026-06-01T00:00:00Z",
    },
    {
        "key": "telegram_bot_enabled",
        "enabled": True,
        "description": "Habilita bot do Telegram",
        "updated_at": "2026-06-01T00:00:00Z",
    },
]

# ─── Flyers ─────────────────────────────────────────────────────────────────

MOCK_FLYERS: list[dict[str, Any]] = [
    {
        "id": "flyer-001",
        "store_name": "Assaí Atacadista",
        "region": "Baixada Santista",
        "city": "Santos",
        "flyer_title": "Oferta Semanal",
        "flyer_date_start": "2026-06-28",
        "flyer_date_end": "2026-07-05",
        "image_url": "https://example.com/flyers/assi/jun28.jpg",
        "image_hash": "abc123def456",
        "image_type": "webp",
        "image_width": 1200,
        "image_height": 1600,
        "ocr_status": "completed",
        "ocr_text": "Leite Condensado Moça 395g R$ 10,50",
        "ocr_confidence": 0.95,
        "products_extracted": 12,
        "source": "tiendeo",
        "valid_from": "2026-06-28",
        "valid_until": "2026-07-05",
        "collected_at": "2026-06-28T08:00:00Z",
        "processed_at": "2026-06-28T08:05:00Z",
    },
]

# ─── Recipes ────────────────────────────────────────────────────────────────

MOCK_RECIPES: list[dict[str, Any]] = [
    {
        "id": "recipe-001",
        "name": "Bolo de Chocolate",
        "yield_qty": 40,
        "overhead_pct": 15.0,
        "profit_pct": 300.0,
        "created_at": "2026-01-15T00:00:00Z",
    },
]

# ─── Recipe Items ───────────────────────────────────────────────────────────

MOCK_RECIPE_ITEMS: list[dict[str, Any]] = [
    {
        "id": "ri-001",
        "recipe_id": "recipe-001",
        "ingredient_id": "ing-001",
        "quantity_g": 395.0,
        "selected_store": "store-001",
        "price_per_kg": 26.58,
    },
    {
        "id": "ri-002",
        "recipe_id": "recipe-001",
        "ingredient_id": "ing-003",
        "quantity_g": 200.0,
        "selected_store": "store-001",
        "price_per_kg": 44.50,
    },
]

# ─── Scrape Frequencies ────────────────────────────────────────────────────

MOCK_SCRAPE_FREQUENCIES: list[dict[str, Any]] = [
    {
        "id": "sf-001",
        "store_id": "store-001",
        "tier": 1,
        "frequency_minutes": 10080,
        "max_retries": 2,
        "timeout_seconds": 30,
        "rate_limit_per_minute": 10,
        "enabled": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    },
    {
        "id": "sf-002",
        "store_id": "store-002",
        "tier": 2,
        "frequency_minutes": 1440,
        "max_retries": 3,
        "timeout_seconds": 60,
        "rate_limit_per_minute": 30,
        "enabled": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    },
]

# ─── Alert Rules ────────────────────────────────────────────────────────────

MOCK_ALERT_RULES: list[dict[str, Any]] = [
    {
        "id": "alert-rule-001",
        "name": "Preço Alto Leite Condensado",
        "channel": "email",
        "trigger": "price_above_threshold",
        "condition": {"ingredient_id": "ing-001", "threshold": 30.0},
        "frequency_minutes": 1440,
        "recipients": [{"channel": "email", "target": "admin@example.com"}],
        "template": "price_alert",
        "enabled": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    },
]

# ─── Alert Recipients ───────────────────────────────────────────────────────

MOCK_ALERT_RECIPIENTS: list[dict[str, Any]] = [
    {
        "id": "alert-recip-001",
        "channel": "email",
        "target": "admin@example.com",
        "name": "Admin",
        "active": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    },
]

# ─── Helpers ────────────────────────────────────────────────────────────────


def copy_mock(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deep-copy a mock list so tests can mutate without side effects."""
    return copy.deepcopy(data)
