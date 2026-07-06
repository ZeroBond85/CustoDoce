#!/usr/bin/env python3
"""
Testes E2E da fila de revisão contra Supabase real.
Cobre: approve, reject, fuzzy match, duplicate price, trigger ON CONFLICT.

Roda com: pytest tests/test_review_queue_e2e.py -v
"""

import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


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


pytestmark = pytest.mark.skipif(
    not _has_db_creds(),
    reason="SUPABASE_URL / SUPABASE_DB_PASSWORD not set",
)


# db_conn removido: usa fixture db_conn de tests/conftest.py (REST via exec_sql_query RPC, porta 443)


# real_supabase removido: usa real_supabase de tests/conftest.py


@pytest.fixture(scope="module")
def test_store(real_supabase):
    """Cria loja de teste temporária."""
    client = real_supabase
    store_id = "_test_review_queue_store"
    client.table("stores").delete().eq("id", store_id).execute()
    client.table("stores").insert(
        {
            "id": store_id,
            "name": "Test Review Queue Store",
            "tier": 99,
        }
    ).execute()
    yield {"id": store_id, "name": "Test Review Queue Store"}
    client.table("stores").delete().eq("id", store_id).execute()


@pytest.fixture(scope="module")
def test_ingredient(real_supabase):
    """Pega um ingrediente real existente."""
    client = real_supabase
    result = client.table("ingredients").select("id, canonical_name").eq("active", True).limit(1).execute()
    assert result.data, "No active ingredients in DB"
    return result.data[0]


# ── 1. Trigger ON CONFLICT — insert + update sem 23505 ──────────


class TestTriggerOnConflict:
    """Testa que o trigger update_history_from_prices() aceita ON CONFLICT."""

    TEST_ING = "_test_trigger_ingredient"
    TEST_STORE_ID = "_test_trigger_store"

    def _cleanup(self, client, db_conn):
        client.table("prices").delete().eq("ingredient_id", self.TEST_ING).execute()
        client.table("price_history").delete().eq("ingredient_id", self.TEST_ING).execute()

    def test_insert_then_update_no_23505(self, real_supabase, db_conn):
        client = real_supabase
        self._cleanup(client, db_conn)
        today = date.today().isoformat()

        # Insert
        r1 = client.rpc(
            "upsert_price_rpc",
            {
                "p_ingredient_id": self.TEST_ING,
                "p_store_id": self.TEST_STORE_ID,
                "p_source": "trigger_test",
                "p_store_name": "Trigger Test Store",
                "p_raw_product": "Trigger Test Product 395g",
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
                "p_normalized": None,
                "p_city": "Test",
                "p_logistics": "pickup_local",
                "p_brand": "TestBrand",
            },
        ).execute()
        assert r1.data, f"First RPC failed: {r1}"

        # Clean price_history from trigger copy before second upsert (via REST - exec_sql_query é SELECT-only)
        (
            client.table("price_history")
            .delete()
            .eq("ingredient_id", self.TEST_ING)
            .eq("store_id", self.TEST_STORE_ID)
            .eq("collected_at", today)
            .execute()
        )

        # Update same key — this was failing with 23505 before PHASE 15 fix
        r2 = client.rpc(
            "upsert_price_rpc",
            {
                "p_ingredient_id": self.TEST_ING,
                "p_store_id": self.TEST_STORE_ID,
                "p_source": "trigger_test",
                "p_store_name": "Trigger Test Store",
                "p_raw_product": "Trigger Test Product UPDATED",
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
                "p_normalized": None,
                "p_city": "Test",
                "p_logistics": "pickup_local",
                "p_brand": "TestBrand",
            },
        ).execute()
        assert r2.data, f"Second RPC failed (was 23505 before fix): {r2}"

        # Verify 1 row in prices
        check = client.table("prices").select("raw_price, raw_product").eq("ingredient_id", self.TEST_ING).execute()
        assert len(check.data) == 1, f"Expected 1 price row, got {len(check.data)}"
        assert check.data[0]["raw_price"] == 15.00

        # Verify 1 row in price_history (from trigger)
        res = (
            client.table("price_history")
            .select("id", count="exact")
            .eq("ingredient_id", self.TEST_ING)
            .eq("store_id", self.TEST_STORE_ID)
            .execute()
        )
        count = res.count or 0
        assert count == 1, f"Expected 1 price_history row (from trigger), got {count}"

        self._cleanup(client, db_conn)

    def test_insert_then_update_without_cleanup(self, real_supabase, db_conn):
        """Real ON CONFLICT test: update without cleaning price_history first."""
        client = real_supabase
        self._cleanup(client, db_conn)
        today = date.today().isoformat()

        # Insert
        r1 = client.rpc(
            "upsert_price_rpc",
            {
                "p_ingredient_id": self.TEST_ING,
                "p_store_id": self.TEST_STORE_ID,
                "p_source": "conflict_test",
                "p_store_name": "Conflict Test Store",
                "p_raw_product": "Conflict Product 395g",
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
                "p_normalized": None,
                "p_city": "Test",
                "p_logistics": "pickup_local",
                "p_brand": "TestBrand",
            },
        ).execute()
        assert r1.data, f"First RPC failed: {r1}"

        # Verify price_history has 1 row from trigger (via Supabase REST)
        count_before = (
            client.table("price_history")
            .select("id", count="exact")
            .eq("ingredient_id", self.TEST_ING)
            .eq("store_id", self.TEST_STORE_ID)
            .execute()
        ).count or 0
        assert count_before == 1, f"Expected 1 price_history row after insert, got {count_before}"

        # Update WITHOUT cleaning price_history — this is the real ON CONFLICT test
        r2 = client.rpc(
            "upsert_price_rpc",
            {
                "p_ingredient_id": self.TEST_ING,
                "p_store_id": self.TEST_STORE_ID,
                "p_source": "conflict_test",
                "p_store_name": "Conflict Test Store",
                "p_raw_product": "Conflict Product UPDATED",
                "p_raw_price": 20.00,
                "p_raw_unit": "un",
                "p_collected_at": today,
                "p_valid_from": today,
                "p_valid_until": today,
                "p_validity_raw": "",
                "p_collected_weekday": "Seg",
                "p_is_promotion": False,
                "p_tier": 99,
                "p_confidence": 1.0,
                "p_normalized": None,
                "p_city": "Test",
                "p_logistics": "pickup_local",
                "p_brand": "TestBrand",
            },
        ).execute()
        assert r2.data, f"Second RPC failed (ON CONFLICT bug): {r2}"

        # Verify price was updated
        check = client.table("prices").select("raw_price").eq("ingredient_id", self.TEST_ING).execute()
        assert len(check.data) == 1
        assert check.data[0]["raw_price"] == 20.00

        # Verify price_history still has 1 row (ON CONFLICT DO UPDATE, not duplicate) — via Supabase REST
        count_after = (
            client.table("price_history")
            .select("id", count="exact")
            .eq("ingredient_id", self.TEST_ING)
            .eq("store_id", self.TEST_STORE_ID)
            .execute()
        ).count or 0
        assert count_after == 1, f"Expected 1 price_history row (ON CONFLICT DO UPDATE), got {count_after}"

        self._cleanup(client, db_conn)


class TestApproveReviewItem:
    """Testa approve_review_item contra banco real."""

    TEST_ING_NAME = None  # set in fixture
    TEST_STORE_ID = "_test_approve_store"

    def _cleanup(self, client, db_conn):
        client.table("review_queue").delete().eq("store_name", "Approve Test Store").execute()
        client.table("price_history").delete().eq("store_id", self.TEST_STORE_ID).execute()
        client.table("prices").delete().eq("store_id", self.TEST_STORE_ID).eq("source", "approve_test").execute()

    def test_approve_with_uuid(self, real_supabase, db_conn, test_store, test_ingredient):
        from services.price_service import approve_review_item

        client = real_supabase

        # Explicit cleanup of specific product to avoid conflict
        client.table("review_queue").delete().eq("raw_product", "Test Approve UUID 200g").execute()

        # Insert review item
        review = (
            client.table("review_queue")
            .upsert(
                {
                    "raw_product": "Test Approve UUID 200g",
                    "raw_price": 8.90,
                    "raw_unit": "un",
                    "store_name": test_store["name"],
                    "source": "approve_test",
                    "confidence": 0.65,
                    "status": "pending",
                    "collected_at": datetime.now(UTC).isoformat(),
                }
            )
            .execute()
        )
        assert review.data, "Failed to insert review item"
        item_id = review.data[0]["id"]

        # Approve with UUID
        result = approve_review_item(item_id, test_ingredient["id"])
        assert result, "approve_review_item returned empty"

        # Verify review status
        check = client.table("review_queue").select("status").eq("id", item_id).execute()
        assert check.data and check.data[0]["status"] == "approved"

        # Verify price was created
        price_check = (
            client.table("prices").select("*").eq("store_id", test_store["id"]).eq("source", "approve_test").execute()
        )
        assert price_check.data, "Price was not created after approve"

        self._cleanup(client, db_conn)

    def test_approve_with_exact_name(self, real_supabase, db_conn, test_store, test_ingredient):
        from services.price_service import approve_review_item

        client = real_supabase

        # Explicit cleanup
        client.table("review_queue").delete().eq("raw_product", "Test Approve Name 500g").execute()

        review = (
            client.table("review_queue")
            .upsert(
                {
                    "raw_product": "Test Approve Name 500g",
                    "raw_price": 12.50,
                    "raw_unit": "un",
                    "store_name": test_store["name"],
                    "source": "approve_test",
                    "confidence": 0.70,
                    "status": "pending",
                    "collected_at": datetime.now(UTC).isoformat(),
                }
            )
            .execute()
        )
        item_id = review.data[0]["id"]

        # Approve with canonical name
        result = approve_review_item(item_id, test_ingredient["canonical_name"])
        assert result, "approve with canonical name returned empty"

        check = client.table("review_queue").select("status").eq("id", item_id).execute()
        assert check.data and check.data[0]["status"] == "approved"

        self._cleanup(client, db_conn)

    def test_approve_with_fuzzy_name(self, real_supabase, db_conn, test_store, test_ingredient):
        from services.price_service import approve_review_item

        client = real_supabase

        # Explicit cleanup
        client.table("review_queue").delete().eq("raw_product", "Test Approve Fuzzy 1kg").execute()

        review = (
            client.table("review_queue")
            .upsert(
                {
                    "raw_product": "Test Approve Fuzzy 1kg",
                    "raw_price": 25.00,
                    "raw_unit": "un",
                    "store_name": test_store["name"],
                    "source": "approve_test",
                    "confidence": 0.55,
                    "status": "pending",
                    "collected_at": datetime.now(UTC).isoformat(),
                }
            )
            .execute()
        )
        item_id = review.data[0]["id"]

        # Approve with typo: add extra chars, swap letters
        canonical = test_ingredient["canonical_name"]
        typo_name = canonical + " X"  # add extra word
        result = approve_review_item(item_id, typo_name)
        assert result, f"approve with fuzzy name '{typo_name}' returned empty"

        check = client.table("review_queue").select("status").eq("id", item_id).execute()
        assert check.data and check.data[0]["status"] == "approved"

        self._cleanup(client, db_conn)

    def test_approve_duplicate_price_no_23505(self, real_supabase, db_conn, test_store, test_ingredient):
        from services.price_service import approve_review_item

        client = real_supabase
        today = date.today().isoformat()

        # Explicit cleanup
        client.table("review_queue").delete().eq("raw_product", "Duplicate Price Product 395g").execute()

        # First: insert a price directly
        client.rpc(
            "upsert_price_rpc",
            {
                "p_ingredient_id": test_ingredient["id"],
                "p_store_id": test_store["id"],
                "p_source": "approve_test",
                "p_store_name": test_store["name"],
                "p_raw_product": "Existing Product 395g",
                "p_raw_price": 9.99,
                "p_raw_unit": "un",
                "p_collected_at": today,
                "p_valid_from": today,
                "p_valid_until": today,
                "p_validity_raw": "",
                "p_collected_weekday": "Seg",
                "p_is_promotion": False,
                "p_tier": 99,
                "p_confidence": 1.0,
                "p_normalized": None,
                "p_city": "Test",
                "p_logistics": "pickup_local",
                "p_brand": "TestBrand",
            },
        ).execute()

        # Clean price_history from trigger copy (via Supabase REST; exec_sql_query é SELECT-only)
        (
            client.table("price_history")
            .delete()
            .eq("ingredient_id", test_ingredient["id"])
            .eq("store_id", test_store["id"])
            .eq("collected_at", today)
            .execute()
        )

        # Now create a review item for the SAME ingredient/store/date
        review = (
            client.table("review_queue")
            .upsert(
                {
                    "raw_product": "Duplicate Price Product 395g",
                    "raw_price": 11.50,
                    "raw_unit": "un",
                    "store_name": test_store["name"],
                    "source": "approve_test",
                    "confidence": 0.60,
                    "status": "pending",
                    "collected_at": datetime.now(UTC).isoformat(),
                }
            )
            .execute()
        )
        item_id = review.data[0]["id"]

        # Approve — this should NOT fail with 23505
        result = approve_review_item(item_id, test_ingredient["id"])
        assert result, "approve duplicate price returned empty (was 23505)"

        # Verify price was updated (not duplicated)
        check = (
            client.table("prices")
            .select("raw_price")
            .eq("ingredient_id", test_ingredient["id"])
            .eq("store_id", test_store["id"])
            .eq("collected_at", today)
            .execute()
        )
        assert len(check.data) == 1, f"Expected 1 price row, got {len(check.data)}"
        assert check.data[0]["raw_price"] == 11.50, "Price was not updated"

        self._cleanup(client, db_conn)


# ── 3. Reject review item ──────────────────────────────────────


class TestRejectReviewItem:
    """Testa reject_review_item contra banco real."""

    def test_reject_sets_status(self, real_supabase, test_store):
        from services.price_service import reject_review_item

        client = real_supabase

        review = (
            client.table("review_queue")
            .insert(
                {
                    "raw_product": "Test Reject Product",
                    "raw_price": 5.00,
                    "raw_unit": "un",
                    "store_name": test_store["name"],
                    "source": "reject_test",
                    "confidence": 0.40,
                    "status": "pending",
                    "collected_at": datetime.now(UTC).isoformat(),
                }
            )
            .execute()
        )
        item_id = review.data[0]["id"]

        result = reject_review_item(item_id)
        assert result, "reject_review_item returned empty"

        check = client.table("review_queue").select("status").eq("id", item_id).execute()
        assert check.data and check.data[0]["status"] == "rejected"

        # Cleanup
        client.table("review_queue").delete().eq("id", item_id).execute()


# ── 4. Add alias ──────────────────────────────────────────────


class TestAddAlias:
    """Testa add_alias_to_ingredient contra banco real."""

    def test_add_alias_to_existing_ingredient(self, real_supabase, test_ingredient):
        from services.config_db import add_alias_to_ingredient

        client = real_supabase

        # Get current aliases
        ing = client.table("ingredients").select("aliases").eq("id", test_ingredient["id"]).execute()
        original_aliases = ing.data[0].get("aliases", []) if ing.data else []
        test_alias = f"_test_alias_{datetime.now(UTC).strftime('%H%M%S')}"

        result = add_alias_to_ingredient(test_ingredient["id"], test_alias)
        assert result, "add_alias_to_ingredient returned empty"

        # Verify alias was added
        check = client.table("ingredients").select("aliases").eq("id", test_ingredient["id"]).execute()
        assert check.data, "Ingredient not found"
        current_aliases = check.data[0].get("aliases", [])
        assert test_alias in current_aliases, f"Alias '{test_alias}' not in {current_aliases}"

        # Restore original aliases
        client.table("ingredients").update({"aliases": original_aliases}).eq("id", test_ingredient["id"]).execute()
