"""
Testes para triggers e constraints no Supabase real.
Cobre: price_history trigger, unique constraints, ON CONFLICT behavior.
"""

import os
import sys
from pathlib import Path
from datetime import date, datetime, UTC

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest


def _has_db_creds():
    url = os.environ.get("SUPABASE_URL", "")
    pwd = os.environ.get("SUPABASE_DB_PASSWORD", "")
    if not url or not pwd:
        return False
    try:
        proj = url.split("//")[1].split(".")[0]
        return len(proj) > 10
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _has_db_creds(), reason="Real DB creds not set")


class TestPriceHistoryTrigger:
    """Testa o trigger update_history_from_prices() no Supabase real."""

    TEST_ING = "_test_trigger_ingredient"
    TEST_STORE_ID = "_test_trigger_store"

    def _cleanup(self, client):
        client.table("prices").delete().eq("ingredient_id", self.TEST_ING).execute()
        client.table("price_history").delete().eq("ingredient_id", self.TEST_ING).execute()

    def test_trigger_copies_price_on_insert(self, real_supabase):
        """Inserir preço deve copiar para price_history via trigger."""
        client = real_supabase
        self._cleanup(client)
        today = date.today().isoformat()

        # Insert via RPC
        r = client.rpc(
            "upsert_price_rpc",
            {
                "p_ingredient_id": self.TEST_ING,
                "p_store_id": self.TEST_STORE_ID,
                "p_source": "trigger_test",
                "p_store_name": "Trigger Test Store",
                "p_raw_product": "Trigger Product 395g",
                "p_raw_price": 10.00,
                "p_raw_unit": "un",
                "p_collected_at": today,
                "p_valid_from": today,
                "p_valid_until": today,
                "p_validity_raw": "",
                "p_collected_weekday": "Seg",
                "p_is_promotion": False,
                "p_tier": 99,
                "p_confidence": 1.0,
                "p_normalized": {"price_per_kg": 10.0, "price_per_un": 10.0, "total_kg": 1.0, "qty": 1},
                "p_city": "Test",
                "p_logistics": "pickup_local",
                "p_brand": "TestBrand",
            },
        ).execute()
        assert r.data, f"RPC failed: {r}"

        # Verify price_history has 1 row
        check = client.table("price_history").select("*").eq("ingredient_id", self.TEST_ING).execute()
        assert len(check.data) == 1, f"Expected 1 price_history row, got {len(check.data)}"
        assert check.data[0]["raw_price"] == 10.00

        self._cleanup(client)

    def test_trigger_updates_history_on_duplicate_key(self, real_supabase):
        """Atualizar preço com mesma chave deve atualizar price_history via trigger."""
        client = real_supabase
        self._cleanup(client)
        today = date.today().isoformat()

        # First insert
        r1 = client.rpc(
            "upsert_price_rpc",
            {
                "p_ingredient_id": self.TEST_ING,
                "p_store_id": self.TEST_STORE_ID,
                "p_source": "trigger_test",
                "p_store_name": "Trigger Test Store",
                "p_raw_product": "Trigger Product 395g",
                "p_raw_price": 10.00,
                "p_raw_unit": "un",
                "p_collected_at": today,
                "p_valid_from": today,
                "p_valid_until": today,
                "p_validity_raw": "",
                "p_collected_weekday": "Seg",
                "p_is_promotion": False,
                "p_tier": 99,
                "p_confidence": 1.0,
                "p_normalized": {"price_per_kg": 10.0, "price_per_un": 10.0, "total_kg": 1.0, "qty": 1},
                "p_city": "Test",
                "p_logistics": "pickup_local",
                "p_brand": "TestBrand",
            },
        ).execute()
        assert r1.data

        # Verify history has 1 row
        check = client.table("price_history").select("*").eq("ingredient_id", self.TEST_ING).execute()
        assert len(check.data) == 1

        # Update same key (should trigger ON CONFLICT DO UPDATE)
        r2 = client.rpc(
            "upsert_price_rpc",
            {
                "p_ingredient_id": self.TEST_ING,
                "p_store_id": self.TEST_STORE_ID,
                "p_source": "trigger_test",
                "p_store_name": "Trigger Test Store",
                "p_raw_product": "Trigger Product UPDATED",
                "p_raw_price": 15.00,
                "p_raw_unit": "un",
                "p_collected_at": today,
                "p_valid_from": today,
                "p_valid_until": today,
                "p_validity_raw": "",
                "p_collected_weekday": "Seg",
                "p_is_promotion": False,
                "p_tier": 99,
                "p_confidence": 1.0,
                "p_normalized": {"price_per_kg": 15.0, "price_per_un": 15.0, "total_kg": 1.0, "qty": 1},
                "p_city": "Test",
                "p_logistics": "pickup_local",
                "p_brand": "TestBrand",
            },
        ).execute()
        assert r2.data

        # Verify price_history still has 1 row (updated, not duplicated)
        check = client.table("price_history").select("*").eq("ingredient_id", self.TEST_ING).execute()
        assert len(check.data) == 1, f"Expected 1 price_history row after update, got {len(check.data)}"
        assert check.data[0]["raw_price"] == 15.00

        self._cleanup(client)

    def test_trigger_different_days_create_multiple_history_rows(self, real_supabase):
        """Mesma loja/ingrediente em dias diferentes deve criar múltiplas linhas em price_history."""
        client = real_supabase
        self._cleanup(client)

        # Day 1
        r1 = client.rpc(
            "upsert_price_rpc",
            {
                "p_ingredient_id": self.TEST_ING,
                "p_store_id": self.TEST_STORE_ID,
                "p_source": "trigger_test",
                "p_store_name": "Trigger Test Store",
                "p_raw_product": "Trigger Product",
                "p_raw_price": 10.00,
                "p_raw_unit": "un",
                "p_collected_at": "2026-06-24",
                "p_valid_from": "2026-06-24",
                "p_valid_until": "2026-07-01",
                "p_validity_raw": "",
                "p_collected_weekday": "Ter",
                "p_is_promotion": False,
                "p_tier": 99,
                "p_confidence": 1.0,
                "p_normalized": {"price_per_kg": 10.0, "price_per_un": 10.0, "total_kg": 1.0, "qty": 1},
                "p_city": "Test",
                "p_logistics": "pickup_local",
                "p_brand": "TestBrand",
            },
        ).execute()
        assert r1.data

        # Day 2
        r2 = client.rpc(
            "upsert_price_rpc",
            {
                "p_ingredient_id": self.TEST_ING,
                "p_store_id": self.TEST_STORE_ID,
                "p_source": "trigger_test",
                "p_store_name": "Trigger Test Store",
                "p_raw_product": "Trigger Product",
                "p_raw_price": 12.00,
                "p_raw_unit": "un",
                "p_collected_at": "2026-06-25",
                "p_valid_from": "2026-06-25",
                "p_valid_until": "2026-07-02",
                "p_validity_raw": "",
                "p_collected_weekday": "Qua",
                "p_is_promotion": False,
                "p_tier": 99,
                "p_confidence": 1.0,
                "p_normalized": {"price_per_kg": 12.0, "price_per_un": 12.0, "total_kg": 1.0, "qty": 1},
                "p_city": "Test",
                "p_logistics": "pickup_local",
                "p_brand": "TestBrand",
            },
        ).execute()
        assert r2.data

        # Verify 2 rows in price_history
        check = (
            client.table("price_history").select("*").eq("ingredient_id", self.TEST_ING).order("collected_at").execute()
        )
        assert len(check.data) == 2, f"Expected 2 price_history rows, got {len(check.data)}"
        assert check.data[0]["raw_price"] == 10.00
        assert check.data[1]["raw_price"] == 12.00

        self._cleanup(client)


class TestUniqueConstraints:
    """Testa constraints UNIQUE no Supabase real."""

    def test_prices_unique_constraint(self, real_supabase):
        """Verifica constraint UNIQUE em prices (ingredient_id, store_id, collected_at)."""
        client = real_supabase
        ing_id = "_test_unique_ing"
        store_id = "_test_unique_store"
        today = date.today().isoformat()

        # Cleanup
        client.table("prices").delete().eq("ingredient_id", ing_id).execute()

        # Insert first
        r1 = client.rpc(
            "upsert_price_rpc",
            {
                "p_ingredient_id": ing_id,
                "p_store_id": store_id,
                "p_source": "constraint_test",
                "p_store_name": "Constraint Test Store",
                "p_raw_product": "Product 1",
                "p_raw_price": 10.00,
                "p_raw_unit": "un",
                "p_collected_at": today,
                "p_valid_from": today,
                "p_valid_until": today,
                "p_validity_raw": "",
                "p_collected_weekday": "Seg",
                "p_is_promotion": False,
                "p_tier": 99,
                "p_confidence": 1.0,
                "p_normalized": {"price_per_kg": 10.0, "price_per_un": 10.0, "total_kg": 1.0, "qty": 1},
                "p_city": "Test",
                "p_logistics": "pickup_local",
                "p_brand": "TestBrand",
            },
        ).execute()
        assert r1.data

        # Update same key should succeed (ON CONFLICT DO UPDATE)
        r2 = client.rpc(
            "upsert_price_rpc",
            {
                "p_ingredient_id": ing_id,
                "p_store_id": store_id,
                "p_source": "constraint_test",
                "p_store_name": "Constraint Test Store",
                "p_raw_product": "Product 2",
                "p_raw_price": 15.00,
                "p_raw_unit": "un",
                "p_collected_at": today,
                "p_valid_from": today,
                "p_valid_until": today,
                "p_validity_raw": "",
                "p_collected_weekday": "Seg",
                "p_is_promotion": False,
                "p_tier": 99,
                "p_confidence": 1.0,
                "p_normalized": {"price_per_kg": 15.0, "price_per_un": 15.0, "total_kg": 1.0, "qty": 1},
                "p_city": "Test",
                "p_logistics": "pickup_local",
                "p_brand": "TestBrand",
            },
        ).execute()
        assert r2.data

        # Verify only 1 row
        check = client.table("prices").select("*").eq("ingredient_id", ing_id).execute()
        assert len(check.data) == 1
        assert check.data[0]["raw_price"] == 15.00

        # Cleanup
        client.table("prices").delete().eq("ingredient_id", ing_id).execute()

    def test_price_history_unique_constraint(self, real_supabase):
        """Verifica constraint UNIQUE em price_history (ingredient_id, store_id, collected_at)."""
        client = real_supabase
        ing_id = "_test_hist_unique_ing"
        store_id = "_test_hist_unique_store"
        today = date.today().isoformat()

        # Cleanup
        client.table("price_history").delete().eq("ingredient_id", ing_id).execute()

        # Insert first
        r1 = client.rpc(
            "upsert_price_rpc",
            {
                "p_ingredient_id": ing_id,
                "p_store_id": store_id,
                "p_source": "hist_constraint_test",
                "p_store_name": "Hist Constraint Store",
                "p_raw_product": "Product 1",
                "p_raw_price": 10.00,
                "p_raw_unit": "un",
                "p_collected_at": today,
                "p_valid_from": today,
                "p_valid_until": today,
                "p_validity_raw": "",
                "p_collected_weekday": "Seg",
                "p_is_promotion": False,
                "p_tier": 99,
                "p_confidence": 1.0,
                "p_normalized": {"price_per_kg": 10.0, "price_per_un": 10.0, "total_kg": 1.0, "qty": 1},
                "p_city": "Test",
                "p_logistics": "pickup_local",
                "p_brand": "TestBrand",
            },
        ).execute()
        assert r1.data

        # Update same key should succeed
        r2 = client.rpc(
            "upsert_price_rpc",
            {
                "p_ingredient_id": ing_id,
                "p_store_id": store_id,
                "p_source": "hist_constraint_test",
                "p_store_name": "Hist Constraint Store",
                "p_raw_product": "Product 2",
                "p_raw_price": 15.00,
                "p_raw_unit": "un",
                "p_collected_at": today,
                "p_valid_from": today,
                "p_valid_until": today,
                "p_validity_raw": "",
                "p_collected_weekday": "Seg",
                "p_is_promotion": False,
                "p_tier": 99,
                "p_confidence": 1.0,
                "p_normalized": {"price_per_kg": 15.0, "price_per_un": 15.0, "total_kg": 1.0, "qty": 1},
                "p_city": "Test",
                "p_logistics": "pickup_local",
                "p_brand": "TestBrand",
            },
        ).execute()
        assert r2.data

        # Verify only 1 row
        check = client.table("price_history").select("*").eq("ingredient_id", ing_id).execute()
        assert len(check.data) == 1

        # Cleanup
        client.table("price_history").delete().eq("ingredient_id", ing_id).execute()


class TestReviewQueueConstraints:
    """Testa constraints e dedup na review_queue."""

    def test_review_queue_dedup_store_product(self, real_supabase):
        """review_queue deve fazer dedup por (store_name, raw_product)."""
        client = real_supabase

        # Cleanup
        client.table("review_queue").delete().eq("store_name", "Dedup Test Store").execute()

        item = {
            "raw_product": "Produto Teste Dedup",
            "raw_price": 5.0,
            "raw_unit": "un",
            "store_name": "Dedup Test Store",
            "source": "dedup_test",
            "confidence": 0.5,
            "status": "pending",
            "collected_at": datetime.now(UTC).isoformat(),
        }

        # First insert
        r1 = client.table("review_queue").insert(item).execute()
        assert r1.data
        assert len(r1.data) == 1

        # Second insert with same store_name + raw_product should trigger constraint
        try:
            client.table("review_queue").insert(item).execute()
        except Exception as e:
            assert "unique constraint" in str(e).lower() or "duplicate key" in str(e).lower()

        # Verify only 1 row remains
        check = client.table("review_queue").select("*").eq("store_name", "Dedup Test Store").execute()
        assert len(check.data) == 1

        # Cleanup
        client.table("review_queue").delete().eq("store_name", "Dedup Test Store").execute()
