import pytest


def pick_restored_cache(primary_key, restore_keys, existing_keys):
    """Simulate actions/cache restore behavior for our use-case:
    - If primary_key exists in existing_keys -> return primary_key
    - Otherwise, find the most recent (max) key in existing_keys that starts with one of the restore_keys (in order)
    - Return None if nothing found
    """
    if primary_key in existing_keys:
        return primary_key
    # Search restore_keys in order; for each, collect matching keys and pick max (simulate most recent)
    for rk in restore_keys:
        matches = [k for k in existing_keys if k.startswith(rk)]
        if matches:
            return max(matches)
    return None


def test_pick_latest_prefixed_cache():
    existing = [
        'state-json-cache-v1-101',
        'state-json-cache-v1-202',
        'state-json-cache-v1-150',
    ]
    primary = 'state-json-cache-v1-303'  # doesn't exist
    restored = pick_restored_cache(primary, ['state-json-cache-v1-'], existing)
    assert restored == 'state-json-cache-v1-202'


def test_primary_key_preferred():
    existing = ['state-json-cache-v1-999', 'state-json-cache-v1-202']
    primary = 'state-json-cache-v1-999'
    restored = pick_restored_cache(primary, ['state-json-cache-v1-'], existing)
    assert restored == primary


def test_no_cache_found():
    existing = []
    primary = 'state-json-cache-v1-1'
    restored = pick_restored_cache(primary, ['state-json-cache-v1-'], existing)
    assert restored is None
