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
