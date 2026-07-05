# `dashboard_queries` — API

> Última atualização: 2026-07-05 16:42 UTC
> Gerado por AST parsing dos serviços em `services/dashboard_queries.py`.

## Funções Públicas (37)

### approve_review_item_cached(item_id: str, ingredient_id: str, brand_override: str)

### cached_get_active_ingredients()

### cached_get_active_recipients(channel)

### cached_get_all_alert_rules(include_disabled)

### cached_get_all_feature_flags()

### cached_get_all_ingredients(include_inactive)

### cached_get_all_recipients(include_inactive)

### cached_get_all_schedules(include_disabled)

### cached_get_all_stores(include_inactive)

### cached_get_enabled_alert_rules(trigger)

### cached_get_enabled_schedules()

### clear_all_caches()

Clear all LRU caches - useful after data mutations.

### extract_ppk(row: dict)

Extract price_per_kg from a row, handling both nested and flat schemas.

### extract_pun(row: dict)

Extract price_per_un from a row, handling both nested and flat schemas.

### get_active_promotions()

Get currently active promotions.

### get_active_stores_by_tier(tier: int | None)

Get active stores, optionally filtered by tier.

### get_cheapest_prices_cached(ingredient: str, top_n: int)

### get_coverage_by_ingredient()

Get coverage statistics per ingredient.

### get_cross_ingredient_ranking_cached(days: int)

### get_dashboard_kpis()

Calculate KPIs for dashboard overview.

### get_ingredient_by_canonical(canonical: str)

Find ingredient by canonical name.

### get_ingredients_with_brands()

Get ingredients with their brands and search terms.

### get_latest_prices_cached(valid_only: bool, limit: int)

Get latest prices using materialized view.

### get_longitudinal_winners_cached(days: int)

### get_price_history_cached(ingredient: str, days: int, valid_only: bool)

### get_price_trends_cached(ingredient: str, days: int)

### get_prices_for_ingredient_cached(ingredient: str, valid_only: bool)

Get prices for an ingredient using the new server-side sorting.

### get_recent_flyers_cached(days: int, source: str | None)

### get_recent_scraper_logs(limit: int)

### get_review_queue_cached(limit: int)

Get review queue using service client for write operations if needed.

### get_scraper_health_dashboard()

Get dashboard-ready scraper health with color-coded status.

### get_store_health()

Get health status for all stores based on recent logs.

### get_store_scraper_config(store_name: str)

Get scraper configuration for a store.

### get_stores_with_frequencies()

Get all stores with their scrape frequencies merged.

### load_ingredients_yaml()

### load_stores_yaml()

### reject_review_item_cached(item_id: str)

