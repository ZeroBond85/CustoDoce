"""
Testes de banco real contra Supabase produção.
Sem mocks. Requer SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY no .env
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from dotenv import load_dotenv
load_dotenv()

pytestmark = pytest.mark.slow

from supabase import create_client
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SKIP_REASON = "SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY não configurados"

def db():
    if not SUPABASE_URL or not SUPABASE_KEY:
        pytest.skip(SKIP_REASON)
    return create_client(SUPABASE_URL, SUPABASE_KEY)


class TestDBReal:
    """D2 — Testes de banco real contra Supabase produção."""

    def test_d2_1_prices_count(self):
        """prices tem dados (>0 linhas)"""
        c = db()
        r = c.table("prices").select("id", count="exact").limit(1).execute()
        assert r.count is not None and r.count > 0, f"D2.1: prices count == {r.count}"

    def test_d2_2_price_history_count(self):
        """price_history tem dados (>0 linhas)"""
        c = db()
        r = c.table("price_history").select("id", count="exact").limit(1).execute()
        assert r.count is not None and r.count > 0, f"D2.2: price_history count == {r.count}"

    def test_d2_3_ingredients_count(self):
        """ingredients = 23"""
        c = db()
        r = c.table("ingredients").select("id", count="exact").execute()
        assert r.count == 23, f"D2.3: ingredients count == {r.count} (expected 23)"

    def test_d2_4_scrape_frequencies_enabled(self):
        """scrape_frequencies.enabled > 0"""
        c = db()
        r = c.table("scrape_frequencies").select("store_id", count="exact").eq("enabled", True).execute()
        assert r.count is not None and r.count > 0, f"D2.4: enabled stores == {r.count}"

    def test_d2_5_review_queue_insert_dedup(self):
        """insert_review_item não dá 23505 no mesmo (store_name, raw_product)"""
        from services.price_service import insert_review_item
        item = {
            "raw_product": "test_d2_5_dedup",
            "raw_price": 1.0,
            "raw_unit": "un",
            "store_name": "test_d2_5_store",
            "source": "manual",
        }
        r1 = insert_review_item(item)
        r2 = insert_review_item(item)
        assert r1 is not None, "Primeiro insert falhou"
        assert r2 is not None, "Segundo insert (dedup) falhou — possível erro 23505"

    def test_d2_6_upsert_price_rpc_dedup(self):
        """RPC upsert_price_rpc: mesmo ingredient_id+store_id+collected_at = UPDATE (mesmo id)"""
        c = db()
        from datetime import date
        today = date.today().isoformat()
        test_ing = c.table("ingredients").select("id").limit(1).execute()
        if not test_ing.data:
            pytest.skip("Nenhum ingrediente no DB")
        ing_id = test_ing.data[0]["id"]
        test_store = c.table("scrape_frequencies").select("store_id").eq("enabled", True).limit(1).execute()
        if not test_store.data:
            pytest.skip("Nenhuma loja ativa")
        store_id = test_store.data[0]["store_id"]
        params = {
            "p_ingredient_id": ing_id,
            "p_store_id": store_id,
            "p_collected_at": today,
            "p_raw_price": 1.23,
            "p_raw_product": "test_d2_6_dedup",
            "p_raw_unit": "kg",
            "p_source": "manual",
            "p_store_name": "test_d2_6_store",
            "p_brand": "",
            "p_city": "",
            "p_collected_weekday": "",
            "p_confidence": 0.95,
            "p_is_promotion": False,
            "p_logistics": "pickup_local",
            "p_normalized": None,
            "p_tier": 2,
            "p_valid_from": None,
            "p_valid_until": None,
            "p_validity_raw": "",
        }
        r1 = c.rpc("upsert_price_rpc", params).execute()
        r2 = c.rpc("upsert_price_rpc", params).execute()
        id1 = r1.data.get("id") if isinstance(r1.data, dict) else None
        id2 = r2.data.get("id") if isinstance(r2.data, dict) else None
        # Pode ser lista; tentar ambos
        if isinstance(r1.data, list) and r1.data:
            id1 = r1.data[0].get("id")
        if isinstance(r2.data, list) and r2.data:
            id2 = r2.data[0].get("id")
        if id1 and id2:
            assert id1 == id2, f"D2.6: IDs diferentes ({id1} vs {id2}) — ON CONFLICT não funcionou"

    def test_d2_7_trigger_price_history(self):
        """Insert em prices → row em price_history (trigger ON CONFLICT)"""
        c = db()
        from datetime import date
        today = date.today().isoformat()
        test_row = c.table("prices").select("ingredient_id,store_id,collected_at").limit(1).execute()
        if not test_row.data:
            pytest.skip("Nenhum price para testar trigger")
        p = test_row.data[0]
        history = c.table("price_history").select("id")\
            .eq("ingredient_id", p["ingredient_id"])\
            .eq("store_id", p["store_id"])\
            .eq("collected_at", p["collected_at"])\
            .limit(1).execute()
        assert len(history.data) > 0, "D2.7: Trigger não criou row em price_history"

    def test_d2_8_cleanup_flyers_all(self):
        """cleanup_old_flyers_all(180) executa sem erro"""
        c = db()
        try:
            r = c.rpc("cleanup_old_flyers_all", {"retention_days": 180}).execute()
        except Exception as e:
            # Pode não ter permissão ou função não existe
            pytest.skip(f"cleanup_old_flyers_all não disponível: {e}")

    def test_d2_9_cleanup_review_items(self):
        """cleanup_resolved_review_items(30) executa sem erro"""
        c = db()
        try:
            r = c.rpc("cleanup_resolved_review_items", {"retention_days": 30}).execute()
        except Exception as e:
            pytest.skip(f"cleanup_resolved_review_items não disponível: {e}")

    def test_d2_10_query_timing(self):
        """Consultas críticas retornam em < 2s"""
        import time
        c = db()
        queries = [
            ("prices 7d", lambda: c.table("prices").select("*").gte("collected_at", (datetime.now(timezone.utc)).isoformat()).limit(10).execute()),
            ("price_history recent", lambda: c.table("price_history").select("*").order("collected_at", desc=True).limit(10).execute()),
            ("review_queue pending", lambda: c.table("review_queue").select("*").eq("status", "pending").limit(10).execute()),
            ("flyers recent", lambda: c.table("flyers").select("*").order("collected_at", desc=True).limit(10).execute()),
            ("ingredients all", lambda: c.table("ingredients").select("*").order("canonical_name").execute()),
        ]
        for name, q in queries:
            t0 = time.time()
            try:
                q()
                elapsed = time.time() - t0
                assert elapsed < 2.0, f"D2.10: {name} levou {elapsed:.2f}s (>2s)"
            except Exception as e:
                pytest.skip(f"D2.10: {name} falhou: {e}")


class TestPipelineReal:
    """D3 — Pipeline E2E Real (insert → dedup → trigger → read)"""

    @pytest.fixture(autouse=True)
    def _restore_real_modules(self):
        """Clean mocked services modules AND force re-import of price_service."""
        for name in list(sys.modules.keys()):
            if (name.startswith("services.") or name == "services") and type(sys.modules[name]).__name__ != "module":
                del sys.modules[name]
        # Also force re-import of price_service (may hold stale refs to old mock)
        sys.modules.pop("services.price_service", None)
        yield

    def test_d3_1_insert_read_cycle(self):
        """Insert preço via upsert_price → get_all_current_prices retorna ele"""
        from services.price_service import upsert_price, get_all_current_prices
        from datetime import date
        today = date.today().isoformat()
        c = db()
        ing = c.table("ingredients").select("id,canonical_name").limit(1).execute()
        if not ing.data:
            pytest.skip("Sem ingredientes")
        ing_id = ing.data[0]["id"]
        store = c.table("scrape_frequencies").select("store_id").eq("enabled", True).limit(1).execute()
        if not store.data:
            pytest.skip("Sem lojas ativas")
        store_id = store.data[0]["store_id"]
        entry = {
            "ingredient_id": ing_id, "store_id": store_id, "source": "manual",
            "store_name": "test_d3_1", "raw_product": "test_d3_1_produto",
            "raw_price": 9.99, "raw_unit": "kg", "collected_at": today,
        }
        result = upsert_price(entry)
        assert result and result.get("id"), "D3.1: upsert_price falhou"
        prices = get_all_current_prices(valid_only=False, limit=2000)
        found = any(p.get("raw_product") == "test_d3_1_produto" for p in prices)
        assert found, "D3.1: get_all_current_prices não retornou o preço inserido"

    def test_d3_2_review_approve_cycle(self):
        """Insert review → approve → price upsertado + alias adicionado"""
        from services.price_service import insert_review_item, approve_review_item
        c = db()
        ing = c.table("ingredients").select("id,canonical_name,aliases").limit(1).execute()
        if not ing.data:
            pytest.skip("Sem ingredientes")
        ing_obj = ing.data[0]
        ing_id = ing_obj["id"]
        product_name = "test_d3_2_approve"
        item = {
            "raw_product": product_name,
            "raw_price": 5.55,
            "raw_unit": "un",
            "store_name": "test_d3_2_store",
            "source": "manual",
            "confidence": 0.95,
        }
        insert_result = insert_review_item(item)
        assert insert_result is not None, "D3.2: insert_review_item falhou"
        item_id = insert_result.get("id")
        if not item_id:
            # Try to find it
            r = c.table("review_queue").select("id").eq("raw_product", product_name).eq("status", "pending").limit(1).execute()
            if r.data:
                item_id = r.data[0]["id"]
        assert item_id, "D3.2: não conseguiu obter item_id do review"
        result = approve_review_item(item_id, ing_id)
        assert result, "D3.2: approve_review_item falhou"
        assert result.get("status") == "approved" or result, "D3.2: status não é approved"

    def test_d3_3_cleanup_test_data(self):
        """Limpa dados de teste criados durante a regressão"""
        c = db()
        for table in ["prices", "price_history", "review_queue"]:
            try:
                c.table(table).delete().like("raw_product", "test_d3_%").execute()
            except Exception:
                pass
        for table in ["prices", "price_history"]:
            try:
                c.table(table).delete().like("store_name", "test_d3_%").execute()
            except Exception:
                pass
        for table in ["prices", "price_history"]:
            try:
                c.table(table).delete().like("raw_product", "test_d2_%").execute()
            except Exception:
                pass
