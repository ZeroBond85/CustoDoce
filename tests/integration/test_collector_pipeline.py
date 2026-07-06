#!/usr/bin/env python3
"""
Testes de integração do pipeline de coleta:
Texto do Produto -> Processamento (Match/Normalize) -> Supabase.
"""

import pytest  # noqa: F401 - pytest fixtures used implicitly


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

    def _setup_store(self, client, store):
        client.table("stores").upsert(store).execute()
        client.table("prices").delete().eq("store_id", store["id"]).execute()
        client.table("price_history").delete().eq("store_id", store["id"]).execute()
        client.table("review_queue").delete().eq("store_name", store["name"]).execute()

    def _cleanup_store(self, client, store):
        client.table("prices").delete().eq("store_id", store["id"]).execute()
        client.table("price_history").delete().eq("store_id", store["id"]).execute()
        client.table("review_queue").delete().eq("store_name", store["name"]).execute()

    def test_pipeline_exact_match(self, real_supabase):
        """Produto com match exato deve ir direto para a tabela prices."""
        client = real_supabase
        from datetime import date

        from services.collector import process_price_match

        store = self._get_test_store("exact")
        self._setup_store(client, store)

        ingredients = client.table("ingredients").select("*").eq("active", True).execute().data
        ing = ingredients[0]
        product_text = f"{ing['canonical_name']} Moça 395g"

        entry = process_price_match(store, product_text, 10.50, "un", ingredients)

        assert entry is not None, f"Falha no match para {product_text}"
        assert entry["ingredient_id"] == ing["canonical_name"]

        # Verifica que EXISTE uma row para (ingredient_id, store_id, collected_at=hoje).
        # Tolerância a dados cumulativos de runs anteriores (collected_at diferente).
        today_iso = date.today().isoformat()
        res = client.table("prices").select("*").eq("store_id", store["id"]).execute()
        today_rows = [r for r in res.data if r.get("collected_at", "")[:10] == today_iso]
        assert len(today_rows) >= 1, (
            f"Expected >=1 price row today={today_iso} para _test_pipeline_store_exact. "
            f"Got {[r.get('collected_at') for r in res.data]}"
        )
        match = next(
            (r for r in today_rows if r.get("raw_product") == product_text and r.get("raw_price") == 10.50),
            None,
        )
        assert match is not None, (
            f"Expected raw_product='{product_text}' raw_price=10.50 today={today_iso}, "
            f"got {[(r.get('raw_product'), r.get('raw_price')) for r in today_rows]}"
        )

        # Cleanup after to ensure test isolation for next runs
        self._cleanup_store(client, store)

    def test_pipeline_fuzzy_match_to_review_queue(self, real_supabase):
        """Produto com confidence baixa deve ir para a review_queue."""
        client = real_supabase
        from services.collector import process_price_match

        store = self._get_test_store("fuzzy")
        self._setup_store(client, store)

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

    def test_pipeline_no_match_ignored(self, real_supabase):
        """Produto sem qualquer relação com ingredientes deve ser ignorado."""
        client = real_supabase
        from services.collector import process_price_match

        store = self._get_test_store("no_match")
        self._setup_store(client, store)

        ingredients = client.table("ingredients").select("*").eq("active", True).execute().data
        product_text = "Parafuso de Aço 10mm"

        entry = process_price_match(store, product_text, 5.00, "un", ingredients)

        assert entry is None

        price_res = client.table("prices").select("*").eq("store_id", store["id"]).execute()
        review_res = client.table("review_queue").select("*").eq("store_name", store["name"]).execute()

        assert len(price_res.data) == 0
        assert len(review_res.data) == 0

        # Cleanup
        self._cleanup_store(client, store)
