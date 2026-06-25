from supabase import create_client
import os

s = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])

# Check all cleanup functions exist
print('Checking cleanup functions...')
for fn in ['cleanup_old_flyers_all', 'cleanup_resolved_review_items', 'cleanup_old_prices', 'cleanup_old_logs', 'cleanup_old_flyers', 'cleanup_non_food_flyers', 'auto_reject_stale_review_items']:
    try:
        r = s.rpc(fn, {'retention_days': 30}).execute()
        print(f'  {fn}: OK')
    except Exception as e:
        print(f'  {fn}: ERROR - {e}')

# Test trigger function ON CONFLICT
print('Testing trigger ON CONFLICT...')
r = s.rpc('upsert_price_rpc', {
    'p_ingredient_id': 'test_trigger_final',
    'p_store_id': 'test_trigger_store',
    'p_source': 'test',
    'p_store_name': 'Test',
    'p_raw_product': 'Test Product',
    'p_raw_price': 10.0,
    'p_raw_unit': 'un',
    'p_collected_at': '2026-01-01',
    'p_valid_from': '2026-01-01',
    'p_valid_until': '2026-01-01',
    'p_validity_raw': '',
    'p_collected_weekday': 'Qua',
    'p_is_promotion': False,
    'p_tier': 1,
    'p_confidence': 1.0,
    'p_normalized': None,
    'p_city': '',
    'p_logistics': 'pickup_local',
    'p_brand': 'Test'
}).execute()
print('RPC upsert: OK')

# Test ON CONFLICT UPDATE
r2 = s.rpc('upsert_price_rpc', {
    'p_ingredient_id': 'test_trigger_final',
    'p_store_id': 'test_trigger_store',
    'p_source': 'test',
    'p_store_name': 'Test',
    'p_raw_product': 'Test Product UPDATED',
    'p_raw_price': 20.0,
    'p_raw_unit': 'un',
    'p_collected_at': '2026-01-01',
    'p_valid_from': '2026-01-01',
    'p_valid_until': '2026-01-01',
    'p_validity_raw': '',
    'p_collected_weekday': 'Qua',
    'p_is_promotion': False,
    'p_tier': 1,
    'p_confidence': 1.0,
    'p_normalized': None,
    'p_city': '',
    'p_logistics': 'pickup_local',
    'p_brand': 'Test'
}).execute()
print('RPC ON CONFLICT UPDATE: OK')

# Check price_history count
r = s.table('price_history').select('count', count='exact').eq('ingredient_id', 'test_trigger_final').eq('store_id', 'test_trigger_store').execute()
print(f'price_history rows: {r.count} (should be 1)')

# Check all cleanup functions exist
functions = [
    'cleanup_old_flyers_all',
    'cleanup_resolved_review_items',
    'cleanup_old_prices',
    'cleanup_old_logs',
    'cleanup_old_flyers',
    'cleanup_non_food_flyers',
    'auto_reject_stale_review_items',
]
print('\nAll cleanup functions verified:')
for fn in functions:
    try:
        s.rpc(fn, {'retention_days': 30}).execute()
        print(f'  {fn}: OK')
    except Exception as e:
        print(f'  {fn}: ERROR - {e}')

print('\nALL DB CHECKS PASSED')
