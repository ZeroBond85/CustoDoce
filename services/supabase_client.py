import os
from typing import Optional

from supabase import Client, create_client


_supabase_client: Optional[Client] = None


def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_ANON_KEY")
        if not url or not key:
            raise ValueError(
                "Supabase URL and key must be set in environment variables. "
                "Set SUPABASE_URL and SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE_KEY."
            )
        _supabase_client = create_client(url, key)
    return _supabase_client


def get_service_client() -> Client:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    url = os.environ.get("SUPABASE_URL")

    if url and key:
        return create_client(url, key)

    return get_supabase()
