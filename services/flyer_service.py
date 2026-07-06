import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from services.logger import logger
from services.supabase_client import get_service_client, get_supabase

_CLEANUP_TRACK_FILE = Path("data/cleanup_track.json")


def _load_cleanup_track() -> dict:
    if _CLEANUP_TRACK_FILE.exists():
        try:
            return json.loads(_CLEANUP_TRACK_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cleanup_track(data: dict):
    _CLEANUP_TRACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CLEANUP_TRACK_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _check_cleanup_alert(cleanup_name: str, deleted: int) -> None:
    """Alert if cleanup deleted 0 rows for 3+ consecutive days."""
    track = _load_cleanup_track()
    today = date.today().isoformat()
    key = f"{cleanup_name}_zero_days"
    if deleted == 0:
        track[key] = track.get(key, 0) + 1
    else:
        track[key] = 0
    track[f"{cleanup_name}_last_run"] = today
    track[f"{cleanup_name}_last_deleted"] = deleted
    _save_cleanup_track(track)
    if track[key] >= 3:
        logger.warning("[ALERT] Cleanup '%s' deleted 0 rows for %d consecutive days", cleanup_name, track[key])


def _upload_flyer_thumbnail(store_name: str, thumbnail_bytes: bytes) -> str:
    """Upload a PNG thumbnail to Supabase Storage and return the public URL."""
    try:
        client = get_service_client()
        safe_name = store_name.lower().replace(" ", "_").replace("/", "_")
        path = f"flyers/{safe_name}_{date.today().isoformat()}.png"
        client.storage.from_("thumbnails").upload(
            path=path,
            file=thumbnail_bytes,
            file_options={"content_type": "image/png", "upsert": "true"},
        )
        url = client.storage.from_("thumbnails").get_public_url(path)
        logger.info("[%s] Thumbnail uploaded: %s", store_name, path)
        return url
    except Exception as e:
        logger.warning("[%s] Thumbnail upload failed: %s", store_name, e)
        return ""


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
        "collected_at": datetime.now(UTC).isoformat(),
    }
    try:
        result = (
            client.table("flyers")
            .upsert(
                data,
                on_conflict="store_name,region,image_hash",
                returning="representation",
            )
            .execute()
        )
        return result.data[0] if result.data else {}
    except Exception:
        return {}


def mark_processed(flyer_id: str, products_count: int = 0) -> dict:
    client = get_service_client()
    try:
        result = (
            client.table("flyers")
            .update(
                {
                    "ocr_status": "done",
                    "products_extracted": products_count,
                    "processed_at": datetime.now(UTC).isoformat(),
                }
            )
            .eq("id", flyer_id)
            .execute()
        )
        return result.data[0] if result.data else {}
    except Exception:
        return {}


def mark_failed(flyer_id: str) -> dict:
    client = get_service_client()
    try:
        result = (
            client.table("flyers")
            .update(
                {
                    "ocr_status": "failed",
                    "processed_at": datetime.now(UTC).isoformat(),
                }
            )
            .eq("id", flyer_id)
            .execute()
        )
        return result.data[0] if result.data else {}
    except Exception:
        return {}


def get_pending_flyers(limit: int = 20) -> list[dict]:
    client = get_supabase()
    result = (
        client.table("flyers")
        .select("*")
        .eq("ocr_status", "pending")
        .order("collected_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data if result.data else []


def cleanup_old_flyers(retention_days: int = 60) -> dict:
    """Deleta flyers com OCR failed mais antigos que retention_days."""
    client = get_service_client()
    try:
        result = client.rpc("cleanup_old_flyers", {"retention_days": retention_days}).execute()
        deleted = result.data if result.data else 0
        _check_cleanup_alert("cleanup_old_flyers", deleted)
        return {"deleted": deleted}
    except Exception:
        _check_cleanup_alert("cleanup_old_flyers", 0)
        return {"deleted": 0}


_NON_FOOD_KEYWORDS = frozenset(
    {
        "boticário",
        "boticario",
        "magazine",
        "casas bahia",
        "renner",
        "riachuelo",
        "marisa",
        "c&a",
        "cea",
        "drogaria",
        "farmacia",
        "farmácia",
        "drogasil",
        "drogão",
        "drogao",
        "polishop",
        "fast shop",
        "electrolux",
        "lg",
        "samsung",
        "sony",
        "posto",
        "gasolina",
        "combustivel",
        "pet",
        "petshop",
        "papelaria",
        "livraria",
        "academia",
        "ótica",
        "otica",
        "oculos",
        "seguros",
        "banco",
        "imobiliária",
        "imobiliaria",
        "imovel",
        "automoveis",
        "carro",
        "moto",
        "cama mesa banho",
        "construcao",
        "construção",
        "presentes",
        "souvenir",
        "brinquedos",
        "perfumaria",
        "cosmeticos",
        "cosméticos",
        "lavanderia",
    }
)


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


def get_recent_flyers(days: int = 7, source: str | None = None) -> list[dict]:
    client = get_supabase()
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    query = client.table("flyers").select("*").gte("collected_at", cutoff).order("collected_at", desc=True)
    if source:
        query = query.eq("source", source)
    result = query.execute()
    return result.data if result.data else []


def get_flyer_detail(flyer_id: str) -> dict:
    """Get detailed flyer information by ID."""
    client = get_supabase()
    result = client.table("flyers").select("*").eq("id", flyer_id).execute()
    return result.data[0] if result.data else {}


def delete_flyer(flyer_id: str) -> dict:
    """Delete a flyer by ID."""
    client = get_service_client()
    try:
        result = client.table("flyers").delete().eq("id", flyer_id).execute()
        return {"deleted": len(result.data) if result.data else 0}
    except Exception:
        return {"deleted": 0}
