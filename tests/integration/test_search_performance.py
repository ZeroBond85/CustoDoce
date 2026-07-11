#!/usr/bin/env python3
"""
Testes de performance para queries críticas.
Valida que search_prices usa server-side sort (não client-side) via generated column.

Requer SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no .env.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


from tests.conftest import _has_real_db as _has_db_creds


pytestmark = [
    pytest.mark.skipif(not _has_db_creds(), reason="Real DB creds not set"),
    pytest.mark.performance,
]


class TestSearchPerformance:
    """Garante que search_prices NÃO faz client-side sort."""

    @pytest.fixture(scope="class")
    def price_service(self):
        """Recarrega price_service sem mocks."""
        for mod in list(sys.modules):
            if mod.startswith("services."):
                sys.modules.pop(mod, None)
        from services import price_service

        return price_service

    def test_search_prices_server_side_sort(self, price_service):
        """ORDER BY price_per_kg deve rodar no Postgres (generated column), não em Python."""
        from services.supabase_client import get_service_client

        client = get_service_client()

        # Busca um ingrediente que realmente tenha preços para testar
        res = client.table("prices").select("ingredient_id").limit(1).execute()
        if not res.data:
            pytest.skip("Tabela prices vazia")

        test_ing_id = res.data[0]["ingredient_id"]
        # Get the canonical name for this ID
        ing_res = client.table("ingredients").select("canonical_name").eq("id", test_ing_id).single().execute()
        if not ing_res.data:
            pytest.skip("Não foi possível encontrar o ingrediente para o preço")

        search_term = ing_res.data["canonical_name"]

        start = time.perf_counter()
        results = price_service.search_prices(search_term, sort_by="price_per_kg", limit=50)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Com generated column + index, espera-se < 500ms em LAN local.
        # Em CI (GitHub Actions + Supabase REST) latência típica 400-800ms.
        # Limite 1500ms cobre flutuação sem esconder regressao: client-side sort
        # leva segundos, nao milissegundos.
        assert elapsed_ms < 1500, f"search_prices levou {elapsed_ms:.0f}ms — provável client-side sort (limite: 1500ms)"
        assert len(results) > 0, f"Nenhum resultado retornado para {search_term}"

        # Verifica que veio ordenado
        prices = [
            r["normalized"]["price_per_kg"]
            for r in results
            if r.get("normalized") and "price_per_kg" in r["normalized"]
        ]
        if prices:
            assert prices == sorted(prices), "Resultados não estão ordenados"

    def test_get_latest_prices_single_query(self, price_service):
        """get_latest_prices deve usar view materializada (1 query rápida)."""
        start = time.perf_counter()
        results = price_service.get_latest_prices(valid_only=True)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 2000, f"get_latest_prices levou {elapsed_ms:.0f}ms — não está usando view (limite: 2000ms)"

    def test_search_by_ingredient_specific(self, price_service):
        """Busca por ingredient_id específico (filtro + index scan)."""
        start = time.perf_counter()
        results = price_service.search_prices("Leite Condensado")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 1500, f"search_prices(ingredient) levou {elapsed_ms:.0f}ms — sem index scan"

    def test_get_price_history_last_30d(self, price_service):
        """Histórico 30 dias com index scan."""
        start = time.perf_counter()
        results = price_service.get_price_history("Leite Condensado", days=30)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # CI típico: 800-2000ms (50 rows + ORDER BY + FK)
        assert elapsed_ms < 3000, f"get_price_history(30d) levou {elapsed_ms:.0f}ms — sem index (limite: 3000ms)"
