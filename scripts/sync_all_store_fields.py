"""Sync all config fields from stores.yaml to DB stores table."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
import yaml
from services.supabase_client import get_service_client

load_dotenv()

FIELDS = [
    'scraper', 'search_url', 'base_url', 'api_endpoint', 'url_pattern',
    'selectors', 'publish_day', 'collection_method', 'visit_frequency',
    'logistics', 'zone', 'coverage', 'contact', 'type', 'priority',
    'verify_ssl', 'headers', 'api_base', 'api_endpoints', 'image_host',
    'is_active',
]

logger = logging.getLogger(__name__)


def sync_store_fields() -> int:
    c = get_service_client()
    yaml_path = Path(__file__).resolve().parent.parent / 'config' / 'stores.yaml'
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    updated = 0
    for s in data['stores']:
        name = s.get('name', '')
        r = c.table('stores').select('id,name').ilike('name', name).maybe_single().execute()
        if not r or not r.data:
            logger.info('MISSING store in DB: %s', name)
            continue
        store_id = r.data['id']
        updates = {}
        for field in FIELDS:
            val = s.get(field)
            if val is not None and val != '':
                if isinstance(val, (list, dict)):
                    val = str(val)
                updates[field] = val
        if updates:
            c.table('stores').update(updates).eq('id', store_id).execute()
            updated += 1

    return updated


def sync_scrape_frequencies() -> int:
    c = get_service_client()
    freqs = [
        ('extra_folheteria', 1, 10080),
        ('pao_de_acucar_fresh', 1, 10080),
        ('dona_dani_ingredientes', 2, 1440),
    ]
    synced = 0
    for store_id, tier, freq in freqs:
        c.table('scrape_frequencies').upsert({
            'store_id': store_id,
            'tier': tier,
            'frequency_minutes': freq,
            'max_retries': 3,
            'timeout_seconds': 120,
            'rate_limit_per_minute': 10,
            'enabled': True,
        }).execute()
        synced += 1
    return synced


if __name__ == "__main__":
    updated = sync_store_fields()
    print(f'{updated} stores updated.')
    synced = sync_scrape_frequencies()
    print(f'{synced} frequencies synced.')
    print('Done: all stores + frequencies synced')
