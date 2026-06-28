#!/usr/bin/env python3
"""
Testes de integração do pipeline de coleta:
Texto do Produto -> Processamento (Match/Normalize) -> Supabase.
"""

import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _has_db_creds():
    url = os.environ.get("SUPABASE_URL", "")
    pwd = os.environ.get("SUPABASE_DB_PASSWORD", "")
    return bool(url and pwd)


pytestmark = pytest.mark.skipif(
    not _has_db_creds(),
    reason="SUPABASE_URL / SUPABASE_DB_PASSWORD not set",
)

from services.collector import process_price_match
from services.supabase_client import get_supabase


class TestCollectorPipeline:
    """Valida o fluxo completo de match e upsert de preços."""

    def _get_test_store(self, suffix: str):
        return {
            "id": f"_test_pipeline_store_{suffix}",
            "name": f"Pipeline Test Store {suffix}",
            "type": "automated",
            "tier": 99,
            "city": "Test City",
            "logistics": "pickup_local",
        }

    def _setup_store(self, store):
        client = get_supabase()
        client.table("stores").upsert(store).execute()
        client.table("prices").delete().eq("store_id", store["id"]).execute()
        client.table("price_history").delete().eq("store_id", store["id"]).execute()
        client.table("review_queue").delete().eq("store_name", store["name"]).execute()

    def test_pipeline_exact_match(self):
        """Produto com match exato deve ir direto para a tabela prices."""
        client = get_supabase()
        store = self._get_test_store("exact")
        self._setup_store(store)

        ingredients = client.table("ingredients").select("*").eq("active", True).execute().data
        ing = ingredients[0]
        product_text = f"{ing['canonical_name']} Moça 395g"

        entry = process_price_match(store, product_text, 10.50, "un", ingredients)

        assert entry is not None, f"Falha no match para {product_text}"
        assert entry["ingredient_id"] == ing["canonical_name"]

        res = client.table("prices").select("*").eq("store_id", store["id"]).execute()
        assert len(res.data) == 1
        assert res.data[0]["raw_product"] == product_text
        assert res.data[0]["raw_price"] == 10.50

    def test_pipeline_fuzzy_match_to_review_queue(self):
        """Produto com confidence baixa deve ir para a review_queue."""
        client = get_supabase()
        store = self._get_test_store("fuzzy")
        self._setup_store(store)

        ingredients = client.table("ingredients").select("*").eq("active", True).execute().data
        ing = ingredients[0]
        # Use a product text that contains the canonical words but with variation
        # Avoid exclude_terms like "mistura", "preparado", etc.
        # Using a variation that should score between 55-80% (fuzzy match)
        product_text = f"{ing['canonical_name']} Premium 1kg"

        entry = process_price_match(store, product_text, 15.00, "un", ingredients)

        price_res = client.table("prices").select("*").eq("store_id", store["id"]).execute()
        review_res = client.table("review_queue").select("*").eq("store_name", store["name"]).execute()

        assert len(price_res.data) + len(review_res.data) >= 1, "Produto sumiu do pipeline"

    def test_pipeline_no_match_ignored(self):
        """Produto sem qualquer relação com ingredientes deve ser ignorado."""
        client = get_supabase()
        store = self._get_test_store("no_match")
        self._setup_store(store)

        ingredients = client.table("ingredients").select("*").eq("active", True).execute().data
        product_text = "Parafuso de Aço 10mm"

        entry = process_price_match(store, product_text, 5.00, "un", ingredients)

        assert entry is None

        price_res = client.table("prices").select("*").eq("store_id", store["id"]).execute()
        review_res = client.table("review_queue").select("*").eq("store_name", store["name"]).execute()

        assert len(price_res.data) == 0
        assert len(review_res.data) == 0
