#!/usr/bin/env python3
"""
Testes de integração para funções de cleanup (TTL) no Supabase.
Valida que registros antigos são removidos e registros novos são mantidos.
"""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from tests.conftest import _has_real_db as _has_db_creds


pytestmark = pytest.mark.skipif(
    not _has_db_creds(),
    reason="SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set",
)


# db_conn removido: usa fixture db_conn de tests/conftest.py (REST via exec_sql_query RPC, porta 443)


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
        client.table("scraping_logs").delete().eq("store_name", store_name).execute()
        client.table("flyers").delete().eq("store_name", store_name).execute()
        client.table("price_history").delete().eq("store_id", store_id).execute()
        client.table("prices").delete().eq("store_id", store_id).execute()
        client.table("stores").delete().eq("id", store_id).execute()

        # Insert store
        client.table("stores").insert({"id": store_id, "name": store_name, "tier": 99}).execute()

        today = datetime.now(UTC).date()
        old_date = today - timedelta(days=100)

        # Prices (trigger copia automaticamente pra price_history)
        client.table("prices").insert(
            {
                "ingredient_id": self.TEST_ING,
                "store_id": store_id,
                "collected_at": today.isoformat(),
                "raw_price": 10.0,
                "raw_product": "New",
            }
        ).execute()
        client.table("prices").insert(
            {
                "ingredient_id": self.TEST_ING,
                "store_id": store_id,
                "collected_at": old_date.isoformat(),
                "raw_price": 5.0,
                "raw_product": "Old",
            }
        ).execute()

        # Logs — sempre com status + finished_at para não deixar órfãos
        # (status='started' sem finished_at polui os dashboards de capacity/health).
        now_iso = datetime.now(UTC).isoformat()
        old_iso = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        client.table("scraping_logs").insert(
            {
                "store_name": store_name,
                "status": "completed",
                "started_at": now_iso,
                "finished_at": now_iso,
                "items_found": 1,
            }
        ).execute()
        client.table("scraping_logs").insert(
            {
                "store_name": store_name,
                "status": "completed",
                "started_at": old_iso,
                "finished_at": old_iso,
                "items_found": 1,
            }
        ).execute()

        if include_flyers:
            client.table("flyers").insert(
                {
                    "store_name": store_name,
                    "region": region,
                    "image_url": f"http://test.com/{unique_id}_1.png",
                    "image_hash": f"hash_{unique_id}_1",
                    "collected_at": datetime.now(UTC).isoformat(),
                }
            ).execute()
            client.table("flyers").insert(
                {
                    "store_name": store_name,
                    "region": region,
                    "image_url": f"http://test.com/{unique_id}_2.png",
                    "image_hash": f"hash_{unique_id}_2",
                    "collected_at": (datetime.now(UTC) - timedelta(days=100)).isoformat(),
                }
            ).execute()

        return store_id, store_name

    def test_cleanup_old_prices(self, real_supabase):
        """Valida cleanup_old_prices(retention_days)."""
        store_id, store_name = self._setup_test_data(real_supabase, include_flyers=False)

        real_supabase.rpc("cleanup_old_prices", {"retention_days": 30}).execute()

        res = real_supabase.table("prices").select("raw_product").eq("ingredient_id", self.TEST_ING).execute()
        products = [r["raw_product"] for r in res.data]

        assert "New" in products
        assert "Old" not in products, "Price antigo não foi removido"

    def test_cleanup_old_logs(self, real_supabase):
        """Valida cleanup_old_logs(retention_days)."""
        store_id, store_name = self._setup_test_data(real_supabase, include_flyers=False)

        real_supabase.rpc("cleanup_old_logs", {"retention_days": 30}).execute()

        res = real_supabase.table("scraping_logs").select("started_at").eq("store_name", store_name).execute()
        today_limit = datetime.now(UTC) - timedelta(days=30)

        for log in res.data:
            started_at = datetime.fromisoformat(log["started_at"].replace("Z", "+00:00"))
            assert started_at > today_limit, f"Log antigo permaneceu: {started_at}"

    def test_cleanup_old_flyers(self, real_supabase):
        """Valida cleanup_old_flyers_all(retention_days)."""
        store_id, store_name = self._setup_test_data(real_supabase, include_flyers=True)

        real_supabase.rpc("cleanup_old_flyers_all", {"retention_days": 30}).execute()

        res = real_supabase.table("flyers").select("collected_at").eq("store_name", store_name).execute()
        today_limit = datetime.now(UTC) - timedelta(days=30)

        for flyer in res.data:
            collected_at = datetime.fromisoformat(flyer["collected_at"].replace("Z", "+00:00"))
            assert collected_at > today_limit, f"Flyer antigo permaneceu: {collected_at}"
