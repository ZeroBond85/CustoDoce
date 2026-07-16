"""Sync all config fields from stores.yaml to DB stores table."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from dotenv import load_dotenv

from services.supabase_client import get_service_client

load_dotenv()

# Campos que existem como colunas na tabela `stores` do Supabase
FIELDS = [
    "scraper",
    "search_url",
    "base_url",
    "api_endpoint",
    "url_pattern",
    "selectors",
    "publish_day",
    "collection_method",
    "visit_frequency",
    "logistics",
    "zone",
    "coverage",
    "contact",
    "type",
    "priority",
    "is_active",
]

# Colunas reais da tabela `stores`. Qualquer outra chave do YAML é config
# específica de scraper (browse_urls, api_base, headers, verify_ssl,
# api_base_fallbacks, image_host_fallbacks, anti_bot, cloudflare, rate_limit,
# vision_timeout_seconds, store_slug, ...) e vai para a coluna `config` (jsonb).
# Sem isso, o scraper em CI perde a configuração e falha (ex: Rede Krill sem
# browse_urls cai no /busca?q= quebrado e retorna 0 produtos).
DB_COLUMNS = {
    "api_endpoint", "base_url", "city", "collection_method", "config", "contact",
    "coverage", "created_at", "id", "is_active", "logistics", "name", "priority",
    "publish_day", "scraper", "search_url", "selectors", "source", "tier", "type",
    "updated_at", "url_pattern", "visit_frequency", "zone",
}

logger = logging.getLogger(__name__)


def sync_store_fields() -> int:
    c = get_service_client()
    yaml_path = Path(__file__).resolve().parent.parent / "config" / "stores.yaml"
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    updated = 0
    for s in data["stores"]:
        name = s.get("name", "")
        r = c.table("stores").select("id,name").ilike("name", name).maybe_single().execute()
        if not r or not r.data:
            logger.info("MISSING store in DB: %s", name)
            continue
        store_id = r.data["id"]
        updates = {}
        for field in FIELDS:
            val = s.get(field)
            if val is not None and val != "":
                updates[field] = val
        # Todas as chaves que não são colunas viram config jsonb (scraper-specific).
        scraper_config = {
            k: v for k, v in s.items() if k not in DB_COLUMNS and v is not None and v != ""
        }
        if scraper_config:
            updates["config"] = scraper_config
        if updates:
            c.table("stores").update(updates).eq("id", store_id).execute()
            updated += 1

    return updated


def _default_frequency_by_tier(tier: int) -> int:
    """Get default frequency_minutes for a store tier."""
    return {1: 10080, 2: 1440, 3: 1440, 4: 43200}.get(tier, 1440)


def sync_scrape_frequencies() -> int:
    """Upsert scrape_frequencies for every active store in YAML.

    Uses the store's actual DB id (queried by name), avoiding slug-drift.
    """
    c = get_service_client()
    yaml_path = Path(__file__).resolve().parent.parent / "config" / "stores.yaml"
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    synced = 0
    for s in data.get("stores", []):
        is_active = s.get("is_active", True)
        if not is_active:
            continue
        name = s.get("name", "")
        if not name:
            continue
        r = c.table("stores").select("id, tier").ilike("name", name).maybe_single().execute()
        if not r or not r.data:
            logger.info("MISSING store in DB: %s — skipping freq", name)
            continue
        store_id = r.data["id"]
        tier = r.data["tier"]
        freq = _default_frequency_by_tier(tier)
        c.table("scrape_frequencies").upsert(
            {
                "store_id": store_id,
                "tier": tier,
                "frequency_minutes": freq,
                "max_retries": 3,
                "timeout_seconds": 120,
                "rate_limit_per_minute": 10,
                "enabled": True,
            },
            on_conflict="store_id",
        ).execute()
        synced += 1

    return synced


if __name__ == "__main__":
    updated = sync_store_fields()
    print(f"{updated} stores updated.")
    synced = sync_scrape_frequencies()
    print(f"{synced} frequencies synced.")
    print("Done: all stores + frequencies synced")
