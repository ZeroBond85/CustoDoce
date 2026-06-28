"""Health check de lojas desativadas — testa se voltaram ao ar.
Roda como parte do cleanup em main.py ou manualmente.
Nao reativa automaticamente — apenas loga para revisao.

Nota: O Supabase stores table nao tem URLs populadas (campo None).
      Usamos stores.yaml como fallback para buscar a URL.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import yaml
from dotenv import load_dotenv

from services.supabase_client import get_service_client  # noqa: E402
from services.config_db import get_all_stores  # noqa: E402

load_dotenv()

logger = logging.getLogger(__name__)

# Cache YAML stores on first load
_yaml_stores = None


def _get_yaml_stores() -> list[dict]:
    global _yaml_stores
    if _yaml_stores is None:
        with open("config/stores.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        _yaml_stores = data if isinstance(data, list) else data.get("stores", [])
    return _yaml_stores


def _lookup_url_from_yaml(store_name: str) -> str:
    """Busca URL da loja no stores.yaml por nome."""
    for s in _get_yaml_stores():
        if s.get("name", "").lower() == store_name.lower():
            return (
                s.get("search_url", "")
                or s.get("base_url", "")
                or s.get("url_pattern", "")
                or s.get("api_endpoint", "")
            )
    return ""


def check_disabled_stores_health(timeout: int = 15) -> list[dict]:
    """Testa HTTP em lojas desativadas. Retorna as que responderam OK."""
    client = get_service_client()
    all_stores = get_all_stores(include_inactive=True)

    # Get disabled store IDs from scrape_frequencies
    freq = client.table("scrape_frequencies").select("*").eq("enabled", False).execute()
    disabled_ids = {f["store_id"] for f in freq.data}
    logger.info("Disabled in scrape_frequencies: %d stores", len(disabled_ids))

    logger.info("All stores returned: %d", len(all_stores))
    matching = [s for s in all_stores if s.get("id", "") in disabled_ids]
    logger.info("Matching stores with disabled_ids: %d", len(matching))

    results = []
    for store in all_stores:
        sid = store.get("id", "")
        if sid not in disabled_ids:
            continue
        name = store.get("name", sid)
        # Try DB first, then YAML fallback
        url = (
            store.get("search_url", "")
            or store.get("base_url", "")
            or store.get("url_pattern", "")
            or store.get("api_endpoint", "")
        )
        if not url:
            url = _lookup_url_from_yaml(name)
        if not url:
            logger.info("[HEALTH] %s -> SEM URL configurada (pulando)", name)
            continue
        if not url.startswith("http"):
            url = "https://" + url

        status = "unknown"
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as h:
                resp = h.head(url)
                status = str(resp.status_code)
        except Exception as e:
            status = str(e)

        entry = {
            "store_id": sid,
            "store_name": name,
            "url": url,
            "status": status,
            "accessible": isinstance(status, int) and status < 500,
        }
        results.append(entry)

        if entry["accessible"]:
            logger.info("[HEALTH] %s -> UP (%s) — candidata a reativacao", name, status)
        else:
            logger.info("[HEALTH] %s -> DOWN (%s)", name, status)

    return results


def reactivate_store(store_id: str) -> bool:
    """Reativa uma loja no scrape_frequencies."""
    client = get_service_client()
    try:
        client.table("scrape_frequencies").update({"enabled": True}).eq("store_id", store_id).execute()
        logger.info("[HEALTH] %s reativada!", store_id)
        return True
    except Exception as e:
        logger.warning("[HEALTH] Erro ao reativar %s: %s", store_id, e)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    results = check_disabled_stores_health()
    print(f"\n=== HEALTH CHECK: {len(results)} lojas testadas ===")
    up = [r for r in results if r["accessible"]]
    down = [r for r in results if not r["accessible"]]
    if up:
        print(f"\n--- UP (possiveis candidatas a reativacao: {len(up)}) ---")
        for r in up:
            print(f"  {r['store_name']:35} HTTP {r['status']}  {r['url']}")
    if down:
        print(f"\n--- DOWN (ainda inacessiveis: {len(down)}) ---")
        for r in down:
            print(f"  {r['store_name']:35} {str(r['status'])[:30]}  {r['url']}")
