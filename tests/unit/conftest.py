import pytest


@pytest.fixture(autouse=True)
def reset_supabase_globals():
    """Reset Supabase client globals before each test to prevent cross-test contamination."""
    import services.supabase_client as sc

    sc._supabase_client = None
    sc._service_client = None
    yield
