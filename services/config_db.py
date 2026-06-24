"""
Database-backed configuration service.
Replaces YAML configs with Supabase tables.
All functions use service_client for write operations.
"""
# mypy: ignore-errors
from datetime import datetime, timezone
from typing import Optional
from services.supabase_client import get_supabase, get_service_client


# ============================================================
# INGREDIENTS
# ============================================================
def get_active_ingredients() -> list[dict]:
    client = get_supabase()
    result = client.table("ingredients").select("*").eq("active", True).order("canonical_name").execute()
    return result.data or []


def get_all_ingredients(include_inactive: bool = False) -> list[dict]:
    client = get_supabase()
    query = client.table("ingredients").select("*").order("canonical_name")
    if not include_inactive:
        query = query.eq("active", True)
    result = query.execute()
    return result.data or []


def get_ingredient_by_id(ingredient_id: str) -> Optional[dict]:
    client = get_supabase()
    result = client.table("ingredients").select("*").eq("id", ingredient_id).maybe_single().execute()
    if result is None:
        return None
    return result.data if result.data else None


def get_ingredient_by_name(canonical_name: str) -> Optional[dict]:
    client = get_supabase()
    result = client.table("ingredients").select("*").eq("canonical_name", canonical_name).maybe_single().execute()
    if result is None:
        return None
    return result.data if result.data else None


def upsert_ingredient(data: dict) -> dict:
    client = get_service_client()
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = client.table("ingredients").upsert(data, on_conflict="canonical_name", returning="representation").execute()
        return result.data[0] if result.data else {}
    except Exception:
        return {}


def delete_ingredient(ingredient_id: str) -> bool:
    client = get_service_client()
    result = client.table("ingredients").delete().eq("id", ingredient_id).execute()
    return bool(result.data)


def add_alias_to_ingredient(canonical_name_or_id: str, new_alias: str) -> Optional[dict]:
    import re
    is_uuid = re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', canonical_name_or_id, re.I)
    ingredient = get_ingredient_by_id(canonical_name_or_id) if is_uuid else None
    if not ingredient:
        ingredient = get_ingredient_by_name(canonical_name_or_id)
    if not ingredient:
        return None

    aliases = ingredient.get("aliases", [])
    if new_alias not in aliases:
        aliases.append(new_alias)
        ingredient["aliases"] = aliases
        return upsert_ingredient(ingredient)
    return ingredient # Return the existing ingredient if alias already present


# ============================================================
# STORES
# ============================================================
def get_active_stores(tier: Optional[int] = None, store_type: Optional[str] = None) -> list[dict]:
    client = get_supabase()
    query = client.table("stores").select("*").eq("is_active", True).order("priority")
    if tier:
        query = query.eq("tier", tier)
    if store_type:
        query = query.eq("type", store_type)
    result = query.execute()
    return result.data or []


def get_all_stores(include_inactive: bool = False) -> list[dict]:
    client = get_supabase()
    query = client.table("stores").select("*").order("priority")
    if not include_inactive:
        query = query.eq("is_active", True)
    result = query.execute()
    return result.data or []


def get_store_by_id(store_id: str) -> Optional[dict]:
    client = get_supabase()
    result = client.table("stores").select("*").eq("id", store_id).maybe_single().execute()
    if result is None:
        return None
    return result.data if result.data else None


def get_store_by_name(name: str) -> Optional[dict]:
    client = get_supabase()
    result = client.table("stores").select("*").eq("name", name).maybe_single().execute()
    if result is None:
        return None
    return result.data if result.data else None


def upsert_store(data: dict) -> dict:
    client = get_service_client()
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = client.table("stores").upsert(data, on_conflict="id", returning="representation").execute()
        return result.data[0] if result.data else {}
    except Exception:
        return {}


def delete_store(store_id: str) -> bool:
    client = get_service_client()
    result = client.table("stores").delete().eq("id", store_id).execute()
    return bool(result.data)


# ============================================================
# SCHEDULES
# ============================================================
def get_enabled_schedules() -> list[dict]:
    client = get_supabase()
    result = client.table("schedules").select("*").eq("enabled", True).order("name").execute()
    return result.data or []


def get_all_schedules(include_disabled: bool = False) -> list[dict]:
    client = get_supabase()
    query = client.table("schedules").select("*").order("name")
    if not include_disabled:
        query = query.eq("enabled", True)
    result = query.execute()
    return result.data or []


def upsert_schedule(data: dict) -> dict:
    client = get_service_client()
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = client.table("schedules").upsert(data, on_conflict="name", returning="representation").execute()
        return result.data[0] if result.data else {}
    except Exception:
        return {}


def delete_schedule(schedule_id: str) -> bool:
    client = get_service_client()
    result = client.table("schedules").delete().eq("id", schedule_id).execute()
    return bool(result.data)


def update_schedule_run(schedule_id: str, last_run: datetime, next_run: Optional[datetime] = None) -> dict:
    client = get_service_client()
    data = {"last_run": last_run.isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
    if next_run:
        data["next_run"] = next_run.isoformat()
    try:
        result = client.table("schedules").update(data).eq("id", schedule_id).execute()
        return result.data[0] if result.data else {}
    except Exception:
        return {}


# ============================================================
# SCRAPE FREQUENCIES
# ============================================================
def get_scrape_frequency(store_id: Optional[str] = None, tier: Optional[int] = None) -> list[dict]:
    client = get_supabase()
    query = client.table("scrape_frequencies").select("*").eq("enabled", True)
    if store_id:
        query = query.eq("store_id", store_id)
    if tier:
        query = query.eq("tier", tier)
    result = query.execute()
    return result.data or []


def upsert_scrape_frequency(data: dict) -> dict:
    client = get_service_client()
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = client.table("scrape_frequencies").upsert(data, returning="representation").execute()
        return result.data[0] if result.data else {}
    except Exception:
        return {}


def delete_scrape_frequency(freq_id: str) -> bool:
    client = get_service_client()
    result = client.table("scrape_frequencies").delete().eq("id", freq_id).execute()
    return bool(result.data)


# ============================================================
# ALERT RECIPIENTS
# ============================================================
def get_active_recipients(channel: Optional[str] = None) -> list[dict]:
    client = get_supabase()
    query = client.table("alert_recipients").select("*").eq("active", True)
    if channel:
        query = query.eq("channel", channel)
    result = query.execute()
    return result.data or []


def get_all_recipients(include_inactive: bool = False) -> list[dict]:
    client = get_supabase()
    query = client.table("alert_recipients").select("*").order("channel, name")
    if not include_inactive:
        query = query.eq("active", True)
    result = query.execute()
    return result.data or []


def upsert_recipient(data: dict) -> dict:
    client = get_service_client()
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = client.table("alert_recipients").upsert(data, returning="representation").execute()
        return result.data[0] if result.data else {}
    except Exception:
        return {}


def delete_recipient(recipient_id: str) -> bool:
    client = get_service_client()
    result = client.table("alert_recipients").delete().eq("id", recipient_id).execute()
    return bool(result.data)


# ============================================================
# ALERT RULES
# ============================================================
def get_enabled_alert_rules(trigger: Optional[str] = None) -> list[dict]:
    client = get_supabase()
    query = client.table("alert_rules").select("*").eq("enabled", True)
    if trigger:
        query = query.eq("trigger", trigger)
    result = query.execute()
    return result.data or []


def get_all_alert_rules(include_disabled: bool = False) -> list[dict]:
    client = get_supabase()
    query = client.table("alert_rules").select("*").order("trigger, name")
    if not include_disabled:
        query = query.eq("enabled", True)
    result = query.execute()
    return result.data or []


def upsert_alert_rule(data: dict) -> dict:
    client = get_service_client()
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = client.table("alert_rules").upsert(data, returning="representation").execute()
        return result.data[0] if result.data else {}
    except Exception:
        return {}


def delete_alert_rule(rule_id: str) -> bool:
    client = get_service_client()
    result = client.table("alert_rules").delete().eq("id", rule_id).execute()
    return bool(result.data)


# ============================================================
# FEATURE FLAGS
# ============================================================
def get_feature_flag(key: str, default: bool = False) -> bool:
    client = get_supabase()
    result = client.table("feature_flags").select("enabled").eq("key", key).maybe_single().execute()
    if result is None:
        return default
    return result.data["enabled"] if result.data else default


def get_all_feature_flags() -> list[dict]:
    client = get_supabase()
    result = client.table("feature_flags").select("*").order("key").execute()
    return result.data or []


def upsert_feature_flag(key: str, enabled: bool, description: str = "") -> dict:
    client = get_service_client()
    data = {"key": key, "enabled": enabled, "description": description, "updated_at": datetime.now(timezone.utc).isoformat()}
    try:
        result = client.table("feature_flags").upsert(data, on_conflict="key", returning="representation").execute()
        return result.data[0] if result.data else {}
    except Exception:
        return {}
