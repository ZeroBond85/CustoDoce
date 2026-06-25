
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.supabase_client import get_supabase, get_service_client


def upsert_flyer(flyer: dict) -> dict:
    client = get_service_client()
    data = {
        "store_name": flyer["store_name"],
        "region": flyer["region"],
        "city": flyer.get("city", ""),
        "flyer_title": flyer.get("flyer_title", ""),
        "flyer_date_start": flyer.get("flyer_date_start"),
        "flyer_date_end": flyer.get("flyer_date_end"),
        "image_url": flyer["image_url"],
        "image_hash": flyer.get("image_hash", ""),
        "image_type": flyer.get("image_type", "webp"),
        "image_width": flyer.get("image_width", 0),
        "image_height": flyer.get("image_height", 0),
        "ocr_status": "pending",
        "source": flyer.get("source", "tiendeo"),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        result = client.table("flyers").upsert(
            data,
            on_conflict="store_name,region,image_hash",
            returning="representation",
        ).execute()
        return result.data[0] if result.data else {}
    except Exception:
        return {}


def mark_processed(flyer_id: str, products_count: int = 0) -> dict:
    client = get_service_client()
    try:
        result = client.table("flyers").update({
            "ocr_status": "done",
            "products_extracted": products_count,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", flyer_id).execute()
        return result.data[0] if result.data else {}
    except Exception:
        return {}


def mark_failed(flyer_id: str) -> dict:
    client = get_service_client()
    try:
        result = client.table("flyers").update({
            "ocr_status": "failed",
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", flyer_id).execute()
        return result.data[0] if result.data else {}
    except Exception:
        return {}


def get_pending_flyers(limit: int = 20) -> list[dict]:
    client = get_supabase()
    result = client.table("flyers").select("*") \
        .eq("ocr_status", "pending") \
        .order("collected_at", desc=True) \
        .limit(limit).execute()
    return result.data if result.data else []


def cleanup_old_flyers(retention_days: int = 60) -> dict:
    """Deleta flyers com OCR failed mais antigos que retention_days."""
    client = get_service_client()
    try:
        result = client.rpc("cleanup_old_flyers", {"retention_days": retention_days}).execute()
        return {"deleted": result.data} if result.data else {"deleted": 0}
    except Exception:
        return {"deleted": 0}


_NON_FOOD_KEYWORDS = frozenset({
    "boticário", "boticario", "magazine", "casas bahia",
    "renner", "riachuelo", "marisa", "c&a", "cea",
    "drogaria", "farmacia", "farmácia", "drogasil", "drogão", "drogao",
    "polishop", "fast shop",
    "electrolux", "lg", "samsung", "sony",
    "posto", "gasolina", "combustivel",
    "pet", "petshop",
    "papelaria", "livraria",
    "academia",
    "ótica", "otica", "oculos",
    "seguros", "banco",
    "imobiliária", "imobiliaria", "imovel",
    "automoveis", "carro", "moto",
    "cama mesa banho",
    "construcao", "construção",
    "presentes", "souvenir",
    "brinquedos",
    "perfumaria", "cosmeticos", "cosméticos",
    "lavanderia",
})


def cleanup_non_food_flyers() -> dict:
    """Deleta flyers de lojas nao-alimenticias (ex: Boticario, Magazine)."""
    client = get_service_client()
    try:
        result = client.table("flyers").select("id, store_name").execute()
        if not result.data:
            return {"deleted": 0}
        to_delete = []
        for f in result.data:
            name = (f.get("store_name") or "").lower().strip()
            if any(kw in name for kw in _NON_FOOD_KEYWORDS):
                to_delete.append(f["id"])
        if not to_delete:
            return {"deleted": 0}
        del_result = client.table("flyers").delete().in_("id", to_delete).execute()
        return {"deleted": len(del_result.data) if del_result.data else 0}
    except Exception:
        return {"deleted": 0}


def get_recent_flyers(days: int = 7, source: Optional[str] = None) -> list[dict]:
    client = get_supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    query = client.table("flyers").select("*") \
        .gte("collected_at", cutoff) \
        .order("collected_at", desc=True)
    if source:
        query = query.eq("source", source)
    result = query.execute()
    return result.data if result.data else []
