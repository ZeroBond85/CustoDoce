"""
Price Service Facade - Maintains backward compatibility by routing calls to specialized services.
"""

from services import price_repository, review_queue_service, price_analytics, maintenance_service, recipe_service

# --- Price Repository ---
upsert_price = price_repository.upsert_price
search_prices = price_repository.search_prices


def get_prices_for_ingredient(ing):
    return price_repository.search_prices(ing, sort_by="price_per_kg", sort_order="asc")


get_latest_prices = price_repository.get_latest_prices
get_all_current_prices = price_repository.get_latest_prices
get_price_history = price_repository.get_price_history
_detect_promotion = price_repository._detect_promotion
_weekday_pt = price_repository._weekday_pt

# --- Review Queue ---
insert_review_item = review_queue_service.insert_review_item
get_review_queue = review_queue_service.get_review_queue
approve_review_item = review_queue_service.approve_review_item
reject_review_item = review_queue_service.reject_review_item
auto_reject_stale_review_items = review_queue_service.auto_reject_stale_review_items

# --- Analytics ---
get_telegram_report = price_analytics.get_telegram_report
get_longitudinal_winners = price_analytics.get_longitudinal_winners
get_price_trends = price_analytics.get_price_trends
get_cross_ingredient_ranking = price_analytics.get_cross_ingredient_ranking


def get_cheapest_prices(ing, top_n=3):
    return price_repository.search_prices(ing, sort_by="price_per_kg", sort_order="asc", limit=top_n, valid_only=True)


# --- Maintenance ---
cleanup_old_prices = maintenance_service.cleanup_old_prices
cleanup_old_logs = maintenance_service.cleanup_old_logs
cleanup_old_flyers_all = maintenance_service.cleanup_old_flyers_all
cleanup_resolved_review_items = maintenance_service.cleanup_resolved_review_items
log_scraper_run = maintenance_service.log_scraper_run
cleanup_test_data = maintenance_service.cleanup_test_data

# --- Recipes ---
upsert_recipe = recipe_service.upsert_recipe
upsert_recipe_item = recipe_service.upsert_recipe_item
