#!/usr/bin/env python3
"""
Testes de integração para funções de cleanup (TTL) no Supabase.
Valida que registros antigos são removidos e registros novos são mantidos.
"""

import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from tests.conftest import _has_real_db as _has_db_creds


pytestmark = pytest.mark.skipif(
    not _has_db_creds(),
    reason="SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set",
)


# db_conn removido: usa fixture db_conn de tests/conftest.py (REST via exec_sql_query RPC, porta 443)

# Erros de rede que valem retry (rerun automático em CI por flakes de infra)
_NETWORK_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
)


def _retry_supabase(callable_obj, retries=3, backoff=1.5):
    """Aplica retry em chamadas encadeadas ``table(...).execute()`` / ``rpc(...)``.

    Supabase REST sobre HTTP/2 derruba conexões silenciosamente (causa
    ``RemoteProtocolError``). Backoff exponencial: 1x, 1.5x, 2.25x (até 3 tentativas)."""
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return callable_obj.execute()
        except _NETWORK_ERRORS as exc:
            last_exc = exc
            if attempt >= retries:
                raise
            time.sleep(backoff ** (attempt - 1))
    raise last_exc  # pragma: no cover


class TestDbCleanup:
    """Valida que as funções de cleanup removem dados antigos corretamente."""

    TEST_ING = "_test_cleanup_ing"

    def _setup_test_data(self, client, include_flyers=False):
        """Cria dados: 1 novo (hoje) e 1 antigo (100 dias atrás)."""
        unique_id = uuid.uuid4().hex
        store_id = f"_test_cleanup_{unique_id[:8]}"
        store_name = f"Cleanup Store {unique_id[:8]}"
        region = f"Region {unique_id[:8]}"

        # Cleanup existing to avoid conflicts — delete in FK-safe order
        _retry_supabase(client.table("scraping_logs").delete().eq("store_name", store_name))
        _retry_supabase(client.table("flyers").delete().eq("store_name", store_name))
        _retry_supabase(client.table("price_history").delete().eq("store_id", store_id))
        _retry_supabase(client.table("prices").delete().eq("store_id", store_id))
        _retry_supabase(client.table("stores").delete().eq("id", store_id))

        # Insert store
        _retry_supabase(client.table("stores").insert({"id": store_id, "name": store_name, "tier": 99}))

        today = datetime.now(UTC).date()
        old_date = today - timedelta(days=100)

        # Prices (trigger copia automaticamente pra price_history)
        _retry_supabase(
            client.table("prices").insert(
                {
                    "ingredient_id": self.TEST_ING,
                    "store_id": store_id,
                    "collected_at": today.isoformat(),
                    "raw_price": 10.0,
                    "raw_product": "New",
                }
            )
        )
        _retry_supabase(
            client.table("prices").insert(
                {
                    "ingredient_id": self.TEST_ING,
                    "store_id": store_id,
                    "collected_at": old_date.isoformat(),
                    "raw_price": 5.0,
                    "raw_product": "Old",
                }
            )
        )

        # Logs — sempre com status + finished_at para não deixar órfãos
        # (status='started' sem finished_at polui os dashboards de capacity/health).
        now_iso = datetime.now(UTC).isoformat()
        old_iso = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        _retry_supabase(
            client.table("scraping_logs").insert(
                {
                    "store_name": store_name,
                    "status": "completed",
                    "started_at": now_iso,
                    "finished_at": now_iso,
                    "items_found": 1,
                }
            )
        )
        _retry_supabase(
            client.table("scraping_logs").insert(
                {
                    "store_name": store_name,
                    "status": "completed",
                    "started_at": old_iso,
                    "finished_at": old_iso,
                    "items_found": 1,
                }
            )
        )

        if include_flyers:
            _retry_supabase(
                client.table("flyers").insert(
                    {
                        "store_name": store_name,
                        "region": region,
                        "image_url": f"http://test.com/{unique_id}_1.png",
                        "image_hash": f"hash_{unique_id}_1",
                        "collected_at": datetime.now(UTC).isoformat(),
                    }
                )
            )
            _retry_supabase(
                client.table("flyers").insert(
                    {
                        "store_name": store_name,
                        "region": region,
                        "image_url": f"http://test.com/{unique_id}_2.png",
                        "image_hash": f"hash_{unique_id}_2",
                        "collected_at": (datetime.now(UTC) - timedelta(days=100)).isoformat(),
                    }
                )
            )

        return store_id, store_name

    def test_cleanup_old_prices(self, real_supabase):
        """Valida cleanup_old_prices(retention_days)."""
        store_id, store_name = self._setup_test_data(real_supabase, include_flyers=False)

        _retry_supabase(real_supabase.rpc("cleanup_old_prices", {"retention_days": 30}))

        res = _retry_supabase(real_supabase.table("prices").select("raw_product").eq("ingredient_id", self.TEST_ING))
        products = [r["raw_product"] for r in res.data]

        assert "New" in products
        assert "Old" not in products, "Price antigo não foi removido"

    def test_cleanup_old_logs(self, real_supabase):
        """Valida cleanup_old_logs(retention_days)."""
        store_id, store_name = self._setup_test_data(real_supabase, include_flyers=False)

        _retry_supabase(real_supabase.rpc("cleanup_old_logs", {"retention_days": 30}))

        res = _retry_supabase(real_supabase.table("scraping_logs").select("started_at").eq("store_name", store_name))
        today_limit = datetime.now(UTC) - timedelta(days=30)

        for log in res.data:
            started_at = datetime.fromisoformat(log["started_at"].replace("Z", "+00:00"))
            assert started_at > today_limit, f"Log antigo permaneceu: {started_at}"

    def test_cleanup_old_flyers(self, real_supabase):
        """Valida cleanup_old_flyers_all(retention_days)."""
        store_id, store_name = self._setup_test_data(real_supabase, include_flyers=True)

        _retry_supabase(real_supabase.rpc("cleanup_old_flyers_all", {"retention_days": 30}))

        res = _retry_supabase(real_supabase.table("flyers").select("collected_at").eq("store_name", store_name))
        today_limit = datetime.now(UTC) - timedelta(days=30)

        for flyer in res.data:
            collected_at = datetime.fromisoformat(flyer["collected_at"].replace("Z", "+00:00"))
            assert collected_at > today_limit, f"Flyer antigo permaneceu: {collected_at}"
