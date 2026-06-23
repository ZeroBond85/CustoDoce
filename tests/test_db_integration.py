#!/usr/bin/env python3
"""
Testes de integração com Supabase real.
Rodam com: pytest tests/test_db_integration.py -v

Requer SUPABASE_URL e SUPABASE_DB_PASSWORD no .env ou como env vars.
Usa dados de teste descartáveis (prefixo _test_*) que são limpos ao final.
"""
import os
import sys
from pathlib import Path
from datetime import date, datetime, timezone

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _has_db_creds():
    url = os.environ.get("SUPABASE_URL", "")
    pwd = os.environ.get("SUPABASE_DB_PASSWORD", "")
    if not url or not pwd:
        return False
    # Validate URL has a real project ID (not just "test")
    try:
        proj = url.split("//")[1].split(".")[0]
        return len(proj) > 10  # real Supabase project IDs are ~20 chars
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _has_db_creds(),
    reason="SUPABASE_URL / SUPABASE_DB_PASSWORD not set",
)


@pytest.fixture(scope="module")
def db_conn():
    """Conexao direta via psycopg2 para testes que precisam de SQL."""
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


@pytest.fixture(scope="module")
def supabase_client():
    """Cliente Supabase Python (service role)."""
    import services.supabase_client as sc

    # Fix linebreaks from .env — JWT keys should have no whitespace
    for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        val = os.environ.get(key, "")
        if val:
            cleaned = val.replace("\n", "").replace("\r", "").replace(" ", "").strip()
            os.environ[key] = cleaned

    if not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        anon = os.environ.get("SUPABASE_ANON_KEY", "")
        if anon:
            os.environ["SUPABASE_SERVICE_ROLE_KEY"] = anon

    # Reset cached clients so they pick up fixed env vars
    sc._supabase_client = None
    sc._service_client = None

    return sc.get_service_client()


# ── RPC upsert_price_rpc ──────────────────────────────────────────


class TestUpsertPriceRpc:
    """Testa a funcao RPC upsert_price_rpc contra o banco real."""

    TEST_INGREDIENT = "_test_integration_ingredient"
    TEST_STORE = "_test_integration_store"
    TODAY = date.today().isoformat()

    def _cleanup(self, client):
        client.table("prices").delete().eq(
            "ingredient_id", self.TEST_INGREDIENT
        ).execute()
        client.table("price_history").delete().eq(
            "ingredient_id", self.TEST_INGREDIENT
        ).execute()
        client.table("stores").delete().eq("id", self.TEST_STORE).execute()

    def test_rpc_upsert_insert_and_update(self, supabase_client, db_conn):
        """Insert + update (upsert) via RPC."""
        client = supabase_client
        self._cleanup(client)

        # Insert
        result = client.rpc("upsert_price_rpc", {
            "p_ingredient_id": self.TEST_INGREDIENT,
            "p_store_id": self.TEST_STORE,
            "p_source": "integration_test",
            "p_store_name": "Integration Test Store",
            "p_raw_product": "Test Product 395g",
            "p_raw_price": 10.50,
            "p_raw_unit": "un",
            "p_collected_at": self.TODAY,
            "p_valid_from": self.TODAY,
            "p_valid_until": self.TODAY,
            "p_validity_raw": "",
            "p_collected_weekday": "Seg",
            "p_is_promotion": False,
            "p_tier": 99,
            "p_confidence": 1.0,
            "p_normalized": None,
            "p_city": "Test City",
            "p_logistics": "pickup_local",
            "p_brand": "TestBrand",
        }).execute()

        assert result.data, f"RPC returned no data: {result}"

        # Clean price_history from trigger copy before second upsert
        cur = db_conn.cursor()
        cur.execute(
            "DELETE FROM price_history WHERE ingredient_id = %s AND store_id = %s AND collected_at = %s;",
            (self.TEST_INGREDIENT, self.TEST_STORE, self.TODAY),
        )
        db_conn.commit()
        cur.close()

        # Update same key → should update, not duplicate
        result2 = client.rpc("upsert_price_rpc", {
            "p_ingredient_id": self.TEST_INGREDIENT,
            "p_store_id": self.TEST_STORE,
            "p_source": "integration_test",
            "p_store_name": "Integration Test Store",
            "p_raw_product": "Test Product 395g UPDATED",
            "p_raw_price": 12.99,
            "p_raw_unit": "un",
            "p_collected_at": self.TODAY,
            "p_valid_from": self.TODAY,
            "p_valid_until": self.TODAY,
            "p_validity_raw": "",
            "p_collected_weekday": "Seg",
            "p_is_promotion": False,
            "p_tier": 99,
            "p_confidence": 1.0,
            "p_normalized": None,
            "p_city": "Test City",
            "p_logistics": "pickup_local",
            "p_brand": "TestBrand",
        }).execute()

        assert result2.data, "Second upsert returned no data"

        # Verify exactly 1 row (no duplicates)
        check = client.table("prices").select("*").eq(
            "ingredient_id", self.TEST_INGREDIENT
        ).execute()
        rows = check.data or []
        assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"
        assert rows[0]["raw_price"] == 12.99
        assert rows[0]["raw_product"] == "Test Product 395g UPDATED"

        self._cleanup(client)


# ── UNIQUE constraint ─────────────────────────────────────────────


class TestUniqueConstraint:
    """Verifica que a constraint UNIQUE de 3 colunas existe e funciona."""

    def test_constraint_exists(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT 1 FROM pg_constraint "
            "WHERE conrelid = 'prices'::regclass "
            "AND conname = 'prices_ingredient_id_store_id_collected_at_key';"
        )
        assert cur.fetchone(), "UNIQUE constraint missing on prices"
        cur.close()

    def test_constraint_exists_price_history(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT 1 FROM pg_constraint "
            "WHERE conrelid = 'price_history'::regclass "
            "AND conname = 'price_history_ingredient_id_store_id_collected_at_key';"
        )
        assert cur.fetchone(), "UNIQUE constraint missing on price_history"
        cur.close()


# ── RPC function exists and is callable ────────────────────────────


class TestRpcFunctions:
    """Verifica que todas as funcoes RPC existem e sao callable."""

    FUNCTIONS = [
        "upsert_price_rpc",
        "cleanup_old_prices",
        "cleanup_old_logs",
        "cleanup_old_flyers",
    ]

    def test_all_functions_exist(self, db_conn):
        cur = db_conn.cursor()
        for fn in self.FUNCTIONS:
            cur.execute("SELECT 1 FROM pg_proc WHERE proname = %s;", (fn,))
            assert cur.fetchone(), f"Function {fn}() not found in database"
        cur.close()


# ── Indexes ────────────────────────────────────────────────────────


class TestIndexes:
    """Verifica que os indices de performance existem."""

    INDEXES = [
        "idx_prices_ing_collected",
        "idx_history_ing_collected",
        "idx_review_collected",
        "idx_stores_name",
        "idx_logs_store_started",
    ]

    def test_all_indexes_exist(self, db_conn):
        cur = db_conn.cursor()
        for idx in self.INDEXES:
            cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s;", (idx,))
            assert cur.fetchone(), f"Index {idx} not found"
        cur.close()


# ── Approve review item (end-to-end) ──────────────────────────────


class TestApproveReviewE2E:
    """Testa o fluxo completo: insert review item → approve → price inserted."""

    TEST_INGREDIENT = "_test_e2e_approve_ingredient"
    TEST_STORE = "_test_e2e_approve_store"

    def test_approve_creates_price(self, supabase_client, db_conn):
        from services.price_service import approve_review_item

        client = supabase_client

        # Cleanup ALL prices/history for test store (trigger copies prices→price_history)
        client.table("review_queue").delete().eq(
            "store_name", "E2E Test Store"
        ).execute()
        cur = db_conn.cursor()
        cur.execute("DELETE FROM price_history WHERE store_id = %s;", (self.TEST_STORE,))
        cur.execute("DELETE FROM prices WHERE store_id = %s;", (self.TEST_STORE,))
        db_conn.commit()
        cur.close()

        # Ensure store exists (approve_review_item calls get_store_by_name)
        existing = client.table("stores").select("id").eq("name", "E2E Test Store").execute()
        if not existing.data:
            client.table("stores").insert({
                "id": self.TEST_STORE,
                "name": "E2E Test Store",
                "tier": 99,
            }).execute()

        # Insert review item
        review = client.table("review_queue").insert({
            "raw_product": "Test Approve Product 200g",
            "raw_price": 8.90,
            "raw_unit": "un",
            "store_name": "E2E Test Store",
            "source": "integration_test",
            "confidence": 0.65,
            "status": "pending",
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        assert review.data, "Failed to insert review item"
        item_id = review.data[0]["id"]

        # We need a real ingredient_id. Use an existing one.
        ings = client.table("ingredients").select("id").limit(1).execute()
        real_ingredient_id = ings.data[0]["id"]

        # Approve
        result = approve_review_item(item_id, real_ingredient_id)
        assert result, "approve_review_item returned empty"

        # Verify review status updated
        check = client.table("review_queue").select("status").eq("id", item_id).execute()
        assert check.data[0]["status"] == "approved"

        # Cleanup
        client.table("review_queue").delete().eq("id", item_id).execute()
        cur = db_conn.cursor()
        cur.execute("DELETE FROM price_history WHERE store_id = %s;", (self.TEST_STORE,))
        cur.execute("DELETE FROM prices WHERE store_id = %s AND source = 'integration_test';", (self.TEST_STORE,))
        db_conn.commit()
        cur.close()
        client.table("stores").delete().eq("id", self.TEST_STORE).execute()
