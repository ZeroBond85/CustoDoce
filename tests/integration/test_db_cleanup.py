#!/usr/bin/env python3
"""
Testes de integração para funções de cleanup (TTL) no Supabase.
Valida que registros antigos são removidos e registros novos são mantidos.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, UTC
import pytest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _has_db_creds():
    url = os.environ.get("SUPABASE_URL", "")
    pwd = os.environ.get("SUPABASE_DB_PASSWORD", "")
    return bool(url and pwd)


pytestmark = pytest.mark.skipif(
    not _has_db_creds(),
    reason="SUPABASE_URL / SUPABASE_DB_PASSWORD not set",
)


@pytest.fixture(scope="module")
def supabase_client():
    """Cliente Supabase (service role)."""
    from services.supabase_client import get_service_client

    return get_service_client()


@pytest.fixture(scope="module")
def db_conn():
    """Conexao direta via psycopg2 para inserts com datas retroativas."""
    import psycopg2

    url = os.environ["SUPABASE_URL"]
    pwd = os.environ["SUPABASE_DB_PASSWORD"]
    proj = url.split("//")[1].split(".")[0]
    conn = psycopg2.connect(
        host=f"db.{proj}.supabase.co",
        dbname="postgres",
        user="postgres",
        password=pwd,
        port=5432,
        connect_timeout=10,
    )
    yield conn
    conn.close()


class TestDbCleanup:
    """Valida que as funções de cleanup removem dados antigos corretamente."""

    TEST_ING = "_test_cleanup_ing"

    def _setup_test_data(self, db_conn, include_flyers=False):
        """Cria dados: 1 novo (hoje) e 1 antigo (100 dias atrás)."""
        cur = db_conn.cursor()

        unique_id = uuid.uuid4().hex
        store_id = f"_test_cleanup_{unique_id[:8]}"
        store_name = f"Cleanup Store {unique_id[:8]}"
        region = f"Region {unique_id[:8]}"

        # Cleanup existing to avoid conflicts
        cur.execute("DELETE FROM flyers WHERE store_name = %s;", (store_name,))
        cur.execute("DELETE FROM scraping_logs WHERE store_name = %s;", (store_name,))

        cur.execute(
            "INSERT INTO stores (id, name, tier) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING;",
            (store_id, store_name, 99),
        )

        # Dates
        today = datetime.now(UTC).date()
        old_date = today - timedelta(days=100)

        # Prices
        cur.execute(
            "INSERT INTO prices (ingredient_id, store_id, collected_at, raw_price, raw_product) VALUES (%s, %s, %s, 10.0, 'New') ON CONFLICT DO NOTHING;",
            (self.TEST_ING, store_id, today),
        )
        cur.execute(
            "INSERT INTO prices (ingredient_id, store_id, collected_at, raw_price, raw_product) VALUES (%s, %s, %s, 5.0, 'Old') ON CONFLICT DO NOTHING;",
            (self.TEST_ING, store_id, old_date),
        )

        # Price History
        cur.execute(
            "INSERT INTO price_history (ingredient_id, store_id, collected_at, raw_price, raw_product) VALUES (%s, %s, %s, 10.0, 'New') ON CONFLICT DO NOTHING;",
            (self.TEST_ING, store_id, today),
        )
        cur.execute(
            "INSERT INTO price_history (ingredient_id, store_id, collected_at, raw_price, raw_product) VALUES (%s, %s, %s, 5.0, 'Old') ON CONFLICT DO NOTHING;",
            (self.TEST_ING, store_id, old_date),
        )

        # Logs
        cur.execute(
            "INSERT INTO scraping_logs (store_name, started_at) VALUES (%s, %s);",
            (store_name, datetime.now(UTC)),
        )
        cur.execute(
            "INSERT INTO scraping_logs (store_name, started_at) VALUES (%s, %s);",
            (store_name, datetime.now(UTC) - timedelta(days=100)),
        )

        if include_flyers:
            # Flyers - use totally unique URLs, content, and image_hash to satisfy unique constraint
            cur.execute(
                "INSERT INTO flyers (store_name, region, image_url, image_hash, collected_at) VALUES (%s, %s, %s, %s, %s);",
                (
                    store_name,
                    region,
                    f"http://test.com/{unique_id}_1.png",
                    f"hash_{unique_id}_1",
                    datetime.now(UTC),
                ),
            )
            cur.execute(
                "INSERT INTO flyers (store_name, region, image_url, image_hash, collected_at) VALUES (%s, %s, %s, %s, %s);",
                (
                    store_name,
                    region,
                    f"http://test.com/{unique_id}_2.png",
                    f"hash_{unique_id}_2",
                    datetime.now(UTC) - timedelta(days=100),
                ),
            )

        db_conn.commit()
        cur.close()
        return store_id, store_name

    def test_cleanup_old_prices(self, supabase_client, db_conn):
        """Valida cleanup_old_prices(retention_days)."""
        store_id, store_name = self._setup_test_data(db_conn, include_flyers=False)

        # Run cleanup with 30 days retention
        supabase_client.rpc("cleanup_old_prices", {"retention_days": 30}).execute()

        # Verify
        res = supabase_client.table("prices").select("raw_product").eq("ingredient_id", self.TEST_ING).execute()
        products = [r["raw_product"] for r in res.data]

        assert "New" in products
        assert "Old" not in products, "Price antigo não foi removido"

    def test_cleanup_old_logs(self, supabase_client, db_conn):
        """Valida cleanup_old_logs(retention_days)."""
        store_id, store_name = self._setup_test_data(db_conn, include_flyers=False)

        supabase_client.rpc("cleanup_old_logs", {"retention_days": 30}).execute()

        # Check logs
        res = supabase_client.table("scraping_logs").select("started_at").eq("store_name", store_name).execute()
        today_limit = datetime.now(UTC) - timedelta(days=30)

        for log in res.data:
            started_at = datetime.fromisoformat(log["started_at"].replace("Z", "+00:00"))
            assert started_at > today_limit, f"Log antigo permaneceu: {started_at}"

    def test_cleanup_old_flyers(self, supabase_client, db_conn):
        """Valida cleanup_old_flyers_all(retention_days)."""
        store_id, store_name = self._setup_test_data(db_conn, include_flyers=True)

        supabase_client.rpc("cleanup_old_flyers_all", {"retention_days": 30}).execute()

        res = supabase_client.table("flyers").select("collected_at").eq("store_name", store_name).execute()
        today_limit = datetime.now(UTC) - timedelta(days=30)

        for flyer in res.data:
            collected_at = datetime.fromisoformat(flyer["collected_at"].replace("Z", "+00:00"))
            assert collected_at > today_limit, f"Flyer antigo permaneceu: {collected_at}"
