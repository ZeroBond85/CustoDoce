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
from datetime import date

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


# db_conn removido: usa fixture db_conn de tests/conftest.py (REST via exec_sql_query RPC, porta 443)


# real_supabase removido: usa real_supabase de tests/conftest.py

# ── RPC upsert_price_rpc ──────────────────────────────────────────


class TestUpsertPriceRpc:
    """Testa a funcao RPC upsert_price_rpc contra o banco real."""

    TEST_INGREDIENT = "_test_integration_ingredient"
    TEST_STORE = "_test_integration_store"
    TODAY = date.today().isoformat()

    def _cleanup(self, client):
        client.table("prices").delete().eq("ingredient_id", self.TEST_INGREDIENT).execute()
        client.table("price_history").delete().eq("ingredient_id", self.TEST_INGREDIENT).execute()
        client.table("stores").delete().eq("id", self.TEST_STORE).execute()

    def test_rpc_upsert_insert_and_update(self, real_supabase, db_conn):
        """Insert + update (upsert) via RPC."""
        client = real_supabase
        self._cleanup(client)

        # Insert
        result = client.rpc(
            "upsert_price_rpc",
            {
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
            },
        ).execute()

        assert result.data, f"RPC returned no data: {result}"

        # Clean price_history from trigger copy before second upsert (via Supabase REST, not raw SQL — exec_sql_query supports SELECT only)
        client.table("price_history").delete().eq("ingredient_id", self.TEST_INGREDIENT).eq(
            "store_id", self.TEST_STORE
        ).eq("collected_at", self.TODAY).execute()

        # Update same key → should update, not duplicate
        result2 = client.rpc(
            "upsert_price_rpc",
            {
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
            },
        ).execute()

        assert result2.data, "Second upsert returned no data"

        # Verify exactly 1 row (no duplicates)
        check = client.table("prices").select("*").eq("ingredient_id", self.TEST_INGREDIENT).execute()
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
# NOTE: Full approve/reject E2E tests are in test_review_queue_e2e.py
# (test_dashboard_full.py poisons sys.modules["services.real_supabase"] with
# a MagicMock at import time, making module reload unreliable in this file.)
