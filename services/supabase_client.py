import os
from pathlib import Path

from supabase import Client, create_client


def _ensure_env_loaded() -> None:
    """Load .env from project root if available (idempotent, no-op if python-dotenv missing)."""
    try:
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
    except ImportError:
        pass


_supabase_client: Client | None = None
_service_client: Client | None = None


def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _ensure_env_loaded()
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise ValueError(
                "Supabase URL and key must be set in environment variables. "
                "Set SUPABASE_URL and SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE_KEY."
            )
        _supabase_client = create_client(url, key)
    return _supabase_client


def get_service_client() -> Client:
    global _service_client
    if _service_client is not None:
        return _service_client
    _ensure_env_loaded()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    url = os.environ.get("SUPABASE_URL")

    if url and key:
        _service_client = create_client(url, key)
        return _service_client

    _service_client = get_supabase()
    return _service_client
