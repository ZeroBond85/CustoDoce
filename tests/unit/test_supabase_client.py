import os
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _reset_client_caches():
    from services import supabase_client

    supabase_client._service_client = None
    supabase_client._supabase_client = None
    yield


@patch("services.supabase_client._ensure_env_loaded", return_value=None)
@patch.dict(os.environ, {}, clear=True)
def test_get_service_client_fails_without_service_role_key(*_):
    from services import supabase_client

    with pytest.raises(ValueError, match="SUPABASE_SERVICE_ROLE_KEY not set"):
        supabase_client.get_service_client()


@patch("services.supabase_client._ensure_env_loaded", return_value=None)
@patch.dict(os.environ, {"SUPABASE_URL": "https://test.supabase.co"}, clear=True)
def test_get_service_client_raises_with_url_but_no_key(*_):
    from services import supabase_client

    with pytest.raises(ValueError, match="SUPABASE_SERVICE_ROLE_KEY not set"):
        supabase_client.get_service_client()


@patch("services.supabase_client.create_client")
@patch("services.supabase_client._ensure_env_loaded", return_value=None)
@patch.dict(
    os.environ,
    {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    },
    clear=True,
)
def test_get_service_client_succeeds_with_key(*args):
    mock_create = args[1]  # create_client is outermost @patch → 2nd arg
    from services import supabase_client

    client = supabase_client.get_service_client()
    assert client is not None
    mock_create.assert_called_once_with(
        "https://test.supabase.co", "test-service-key"
    )
