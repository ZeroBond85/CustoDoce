#!/usr/bin/env python3
"""
Seed script to populate config tables from YAML files.
Run after applying migration 001_config_tables.sql
"""
import os
import sys
import yaml
from pathlib import Path

from services.config_db import (
    upsert_ingredient,
    upsert_store,
    upsert_schedule,
    upsert_scrape_frequency,
    upsert_feature_flag,
)

# Add repo root to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

os.environ.setdefault("SUPABASE_URL", "https://xxx.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "xxx")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "xxx")


def seed_ingredients():
    """Seed ingredients from config/ingredients.yaml"""
    with open(repo_root / "config" / "ingredients.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    for ing in data.get("ingredients", []):
        upsert_ingredient({
            "canonical_name": ing["canonical"],
            "category": ing.get("category", ""),
            "aliases": ing.get("aliases", []),
            "unit_target": ing.get("unit_target", "kg"),
            "active": True,
        })
        print(f"  ✓ Ingredient: {ing['canonical']}")


def seed_stores():
    """Seed stores from config/stores.yaml"""
    with open(repo_root / "config" / "stores.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    for store in data.get("stores", []):
        units = store.get("units", [])
        cities = store.get("cities", [])
        # Extract city from first city or first unit address
        city = ""
        zone = ""
        if cities:
            city = cities[0]
        elif units and units[0].get("address"):
            addr = units[0]["address"]
            # Extract city from address (format: "Av. ..., Bairro, Cidade")
            parts = [p.strip() for p in addr.split(",")]
            if len(parts) >= 2:
                city = parts[-1]
                zone = parts[-2]
        elif store.get("city"):
            city = store.get("city", "")
            zone = store.get("zone", "")

        store_data = {
            "name": store["name"],
            "tier": store.get("tier", 2),
            "type": store.get("type", "website_catalog"),
            "logistics": store.get("logistics", "pickup_local"),
            "city": city,
            "zone": zone,
            "url_pattern": store.get("url_pattern", ""),
            "base_url": store.get("base_url", ""),
            "api_endpoint": store.get("api_endpoint", ""),
            "search_url": store.get("search_url", ""),
            "selectors": store.get("selectors", {}),
            "publish_day": store.get("publish_day", ""),
            "collection_method": store.get("collection_method", "automated"),
            "visit_frequency": store.get("visit_frequency", ""),
            "scraper": store.get("scraper", ""),
            "contact": store.get("contact", ""),
            "coverage": store.get("coverage", ""),
            "priority": store.get("priority", 99),
            "is_active": store.get("is_active", True),
        }
        upsert_store(store_data)
        status = "✓" if store_data["is_active"] else "⊘"
        print(f"  {status} Store: {store['name']} (Tier {store_data['tier']})")


def seed_schedules():
    """Seed default schedules (matching GitHub Actions cron)"""
    schedules = [
        {
            "name": "coleta_diaria_tier1_2a",
            "cron_expression": "0 12 * * 1,3,5",
            "timezone": "America/Sao_Paulo",
            "payload": {"force_full": False, "run_playwright": False, "tiers": [1, 2]},
            "enabled": True,
        },
        {
            "name": "coleta_semanal_playwright_ocr",
            "cron_expression": "0 12 * * 6",
            "timezone": "America/Sao_Paulo",
            "payload": {"force_full": False, "run_playwright": True, "tiers": [3]},
            "enabled": True,
        },
        {
            "name": "relatorio_mensal_release",
            "cron_expression": "0 12 1 * *",
            "timezone": "America/Sao_Paulo",
            "payload": {"force_full": False, "run_playwright": False, "monthly_release": True},
            "enabled": True,
        },
    ]
    for s in schedules:
        upsert_schedule(s)
        print(f"  ✓ Schedule: {s['name']} ({s['cron_expression']})")


def seed_scrape_frequencies():
    """Seed default scrape frequencies per tier"""
    defaults = [
        {"tier": 1, "frequency_minutes": 1440, "max_retries": 2, "timeout_seconds": 30, "rate_limit_per_minute": 5, "enabled": True},
        {"tier": 2, "frequency_minutes": 1440, "max_retries": 2, "timeout_seconds": 30, "rate_limit_per_minute": 10, "enabled": True},
        {"tier": 3, "frequency_minutes": 1440, "max_retries": 1, "timeout_seconds": 60, "rate_limit_per_minute": 5, "enabled": True},
        {"tier": 4, "frequency_minutes": 10080, "max_retries": 0, "timeout_seconds": 0, "rate_limit_per_minute": 0, "enabled": False},
    ]
    for d in defaults:
        upsert_scrape_frequency(d)
        print(f"  ✓ Scrape Frequency: Tier {d['tier']} every {d['frequency_minutes']} min")


def seed_feature_flags():
    """Seed feature flags from config/features.yaml"""
    features_file = repo_root / "config" / "features.yaml"
    if features_file.exists():
        with open(features_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for key, enabled in data.get("features", {}).items():
            upsert_feature_flag(key, bool(enabled), "")
            print(f"  ✓ Feature: {key} = {enabled}")
    else:
        defaults = {
            "scrapers_enabled": True,
            "telegram_bot_enabled": True,
            "email_reports_enabled": True,
            "alerts_enabled": True,
            "export_enabled": True,
            "review_queue_enabled": True,
        }
        for key, enabled in defaults.items():
            upsert_feature_flag(key, enabled, "")
            print(f"  ✓ Feature (default): {key} = {enabled}")


def seed_alerts():
    """Seed default alert rules and recipients (empty - user configures via dashboard)"""
    print("  ℹ Alert recipients & rules: configure via dashboard (tab_alertas)")


def main():
    print("🌱 Seeding config database...")
    print("\n📦 Ingredients:")
    seed_ingredients()

    print("\n🏪 Stores:")
    seed_stores()

    print("\n⏰ Schedules:")
    seed_schedules()

    print("\n🔄 Scrape Frequencies:")
    seed_scrape_frequencies()

    print("\n🚩 Feature Flags:")
    seed_feature_flags()

    print("\n🔔 Alerts:")
    seed_alerts()

    print("\n✅ Seeding complete!")


if __name__ == "__main__":
    main()
