"""Unit test configuration."""

import os

# Fast password hashing for tests (600k -> 4 iterations, ~0.5s -> ~0.001s)
os.environ.setdefault("AUTH_PBKDF2_ITERATIONS", "4")

import pytest  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def reset_supabase_globals():
    """Reset Supabase client globals before each test to prevent cross-test contamination."""
    import services.supabase_client as sc

    sc._supabase_client = None
    sc._service_client = None
    yield


@pytest.fixture(autouse=True)
def cleanup_test_ingredients():
    """Clean up test ingredients from DB after each test to prevent pollution."""
    yield
    # Function-scoped teardown for integration tests
    try:
        from services.supabase_client import get_service_client
        client = get_service_client()
        # Clean test ingredients (prefix _test_)
        client.table("ingredients").delete().like("canonical_name", "_test_%").execute()
        # Clean test stores
        client.table("stores").delete().like("name", "%Test Store%").execute()
        client.table("stores").delete().like("name", "%Test%").execute()
    except Exception:
        pass  # Best effort cleanup
