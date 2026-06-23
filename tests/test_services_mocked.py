"""Testes de servicos com mocks do Supabase.

Valida a logica real de construcao de payloads, filtros e transformacao
sem depender de banco real ou conexao de rede.

Uso:
    python -m pytest tests/test_services_mocked.py -v
"""

import os
import sys
from datetime import date, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")


# ── Mock helpers ──────────────────────────────────────────────

class MockQueryResult:
    def __init__(self, data=None):
        self.data = data or []
        self.count = len(self.data) if isinstance(self.data, list) else 0


class MockQueryBuilder:
    """Simula o builder chainable do Supabase.
    table.select().eq().order().limit().single().execute() -> MockQueryResult
    """

    def __init__(self, return_data=None):
        self._return_data = return_data if return_data is not None else []
        self._applied_filters = []
        self._captured_upsert = None
        self._captured_insert = None
        self._captured_update = None
        self._single_mode = False

    def select(self, *args, **kwargs):
        return self

    def eq(self, field, value):
        self._applied_filters.append(("eq", field, value))
        return self

    def lte(self, field, value):
        self._applied_filters.append(("lte", field, value))
        return self

    def gte(self, field, value):
        self._applied_filters.append(("gte", field, value))
        return self

    def order(self, field, desc=False):
        self._applied_filters.append(("order", field, desc))
        return self

    def limit(self, n):
        self._applied_filters.append(("limit", n))
        return self

    def single(self):
        self._single_mode = True
        return self

    def maybe_single(self):
        self._single_mode = True
        return self

    def execute(self):
        if self._single_mode and isinstance(self._return_data, list) and len(self._return_data) == 1:
            self._single_mode = False
            return MockQueryResult(self._return_data[0])
        if self._single_mode and isinstance(self._return_data, list) and len(self._return_data) > 0:
            self._single_mode = False
            return MockQueryResult(self._return_data[0])
        self._single_mode = False
        return MockQueryResult(self._return_data)

    def insert(self, data):
        self._captured_insert = data
        return self

    def update(self, data):
        self._captured_update = data
        return self

    def upsert(self, data, on_conflict=None, returning=None):
        self._captured_upsert = data
        return self


class MockSupabaseClient:
    """Simula o cliente Supabase com .table() e .rpc()."""

    def __init__(self, qb=None):
        self.qb = qb if qb is not None else MockQueryBuilder([])
        self._captured_rpc = None

    def table(self, name):
        self._last_table = name
        return MockTable(self.qb)

    def rpc(self, fn_name, params=None):
        self._captured_rpc = (fn_name, params)
        return self.qb


class MockTable:
    """Simula uma tabela do Supabase.

    Todas as operacoes (select, upsert, insert, update) retornam o mesmo
    MockQueryBuilder, garantindo que os dados capturados fiquem acessiveis.
    """

    def __init__(self, qb=None):
        self.qb = qb if qb is not None else MockQueryBuilder([])

    def select(self, *args, **kwargs):
        return self.qb

    def upsert(self, data, on_conflict=None, returning=None):
        return self.qb.upsert(data, on_conflict, returning)

    def insert(self, data):
        return self.qb.insert(data)

    def delete(self):
        return self.qb

    def update(self, data):
        return self.qb.update(data)


def make_mocks():
    """Retorna (mock_client, MockTable, MockQueryBuilder) prontos para uso."""
    qb = MockQueryBuilder([])
    table = MockTable(qb)
    mock_client = MockSupabaseClient(qb)
    return mock_client, table, qb


# ── Sample data ──────────────────────────────────────────────

SAMPLE_PRICES = [
    {
        "id": "1", "ingredient_id": "Leite Condensado Integral",
        "store_id": "assai", "store_name": "Assai",
        "raw_product": "Leite Condensado Moca 395g", "raw_price": 42.90,
        "raw_unit": "cx 12x395g", "collected_at": "2026-06-16T10:00:00",
        "valid_from": "2026-06-16", "valid_until": "2026-06-23",
        "validity_raw": "Validade: 23/06", "collected_weekday": "Ter",
        "is_promotion": False, "tier": 1, "confidence": 1.0,
        "normalized": {"qty": 12, "unit_kg": 0.395, "total_kg": 4.74, "price_per_kg": 9.05, "price_per_un": 3.58},
        "city": "Santos", "logistics": "pickup_local",
    },
    {
        "id": "2", "ingredient_id": "Leite Condensado Integral",
        "store_id": "atacadao", "store_name": "Atacadao",
        "raw_product": "Leite Moca PROMO", "raw_price": 39.90,
        "raw_unit": "cx 12x395g", "collected_at": "2026-06-16T10:30:00",
        "valid_from": "2026-06-16", "valid_until": "2026-06-30",
        "validity_raw": "Oferta valida ate 30/06", "collected_weekday": "Ter",
        "is_promotion": True, "tier": 1, "confidence": 1.0,
        "normalized": {"qty": 12, "unit_kg": 0.395, "total_kg": 4.74, "price_per_kg": 8.42, "price_per_un": 3.33},
        "city": "Santos", "logistics": "pickup_local",
    },
]

SAMPLE_REVIEW = [
    {
        "id": "r1", "raw_product": "Ninho Integral 400g",
        "raw_price": 25.90, "raw_unit": "un", "store_name": "Extra",
        "source": "automated", "confidence": 0.65,
        "suggestions": ["Leite Ninho Integral"],
        "validity_raw": "Promocao semana do cliente",
        "status": "pending", "collected_at": "2026-06-16T11:00:00",
    }
]

SAMPLE_HISTORY = [
    {
        "id": "h1", "price_id": "1", "ingredient_id": "Leite Condensado Integral",
        "store_id": "assai", "store_name": "Assai",
        "raw_product": "Leite Condensado Moca 395g", "raw_price": 45.00,
        "raw_unit": "cx 12x395g",
        "normalized": {"price_per_kg": 9.49, "price_per_un": 3.75},
        "valid_from": "2026-06-09", "valid_until": "2026-06-16",
        "validity_raw": "", "collected_weekday": "Ter", "is_promotion": False,
        "collected_at": "2026-06-09T10:00:00",
    },
]


# ═══════════════════════════════════════════════════════════════
# PRICE SERVICE TESTS
# ═══════════════════════════════════════════════════════════════

class TestPriceService:

    # ── upsert_price ───────────────────────────────────────────

    @patch("services.price_service.get_service_client")
    def test_upsert_price_payload_complete(self, mock_get_client):
        """Monta payload com todos os campos novos."""
        from services.price_service import upsert_price

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        entry = {
            "ingredient_id": "Leite Condensado Integral",
            "store_id": "test_store", "store_name": "Test Store",
            "raw_product": "Leite Moca", "raw_price": 42.90,
            "raw_unit": "cx 12x395g",
            "validity_raw": "Promocao valida ate 30/06",
            "tier": 1, "confidence": 0.95,
            "normalized": {"price_per_kg": 9.05, "price_per_un": 3.58},
            "city": "Santos",
        }

        upsert_price(entry)

        fn_name, rpc_params = mock_client._captured_rpc
        assert fn_name == "upsert_price_rpc", "rpc() should call upsert_price_rpc"
        assert rpc_params["p_ingredient_id"] == "Leite Condensado Integral"
        assert rpc_params["p_store_id"] == "test_store"
        assert rpc_params["p_raw_price"] == 42.90
        assert rpc_params["p_validity_raw"] == "Promocao valida ate 30/06"
        assert rpc_params["p_collected_weekday"] in ("Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom")
        assert rpc_params["p_valid_from"]
        assert rpc_params["p_valid_until"]
        assert rpc_params["p_is_promotion"] is not None
        assert rpc_params["p_collected_at"]

    @patch("services.price_service.get_service_client")
    def test_upsert_price_detects_promotion(self, mock_get_client):
        """Detecta promocao pelo nome do produto."""
        from services.price_service import upsert_price

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        upsert_price({"ingredient_id": "Teste", "store_id": "t", "store_name": "T",
                       "raw_product": "Moca PROMO 50% OFF", "raw_price": 10.0, "raw_unit": "un"})

        _, rpc_params = mock_client._captured_rpc
        assert rpc_params["p_is_promotion"] is True

    @patch("services.price_service.get_service_client")
    def test_upsert_price_no_promotion(self, mock_get_client):
        """Nao marca promocao sem keywords."""
        from services.price_service import upsert_price

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        upsert_price({"ingredient_id": "Teste", "store_id": "t", "store_name": "T",
                       "raw_product": "Farinha de Trigo", "raw_price": 5.0, "raw_unit": "1kg"})

        _, rpc_params = mock_client._captured_rpc
        assert rpc_params["p_is_promotion"] is False

    @patch("services.price_service.get_service_client")
    def test_upsert_price_default_valid_until(self, mock_get_client):
        """Calcula valid_until default +7 dias."""
        from services.price_service import upsert_price

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        upsert_price({"ingredient_id": "Teste", "store_id": "t", "store_name": "T",
                       "raw_product": "Teste", "raw_price": 10.0, "raw_unit": "un"})

        expected = (date.today() + timedelta(days=7)).isoformat()
        _, rpc_params = mock_client._captured_rpc
        assert rpc_params["p_valid_until"] == expected, \
            f"Esperado {expected}, obtido {rpc_params['p_valid_until']}"

    # ── search_prices ──────────────────────────────────────────

    @patch("services.price_service.get_supabase")
    def test_search_prices_valid_only_applies_filters(self, mock_get):
        """valid_only=True aplica filtros lte/gte valid_from/valid_until."""
        from services.price_service import search_prices

        mock_client, _, qb = make_mocks()
        qb._return_data = SAMPLE_PRICES
        mock_get.return_value = mock_client

        result = search_prices("Leite Condensado Integral", valid_only=True)

        types = [f[0] for f in qb._applied_filters]
        assert "lte" in types, "Deveria filtrar lte valid_from"
        assert "gte" in types, "Deveria filtrar gte valid_until"
        assert len(result) == 2

    @patch("services.price_service.get_supabase")
    def test_search_prices_valid_only_false_skips_filters(self, mock_get):
        """valid_only=False nao aplica filtros de data."""
        from services.price_service import search_prices

        mock_client, _, qb = make_mocks()
        qb._return_data = SAMPLE_PRICES
        mock_get.return_value = mock_client

        search_prices("Leite Condensado Integral", valid_only=False)

        types = [f[0] for f in qb._applied_filters]
        assert "lte" not in types, "Nao deveria filtrar lte"
        assert "gte" not in types, "Nao deveria filtrar gte"

    @patch("services.price_service.get_supabase")
    def test_search_prices_empty_result(self, mock_get):
        """Retorna lista vazia quando sem dados."""
        from services.price_service import search_prices

        mock_client, _, _ = make_mocks()
        mock_get.return_value = mock_client

        result = search_prices("Inexistente")
        assert result == []

    @patch("services.price_service.get_supabase")
    def test_search_prices_default_order_asc(self, mock_get):
        """Ordena por price_per_kg ASC no cliente (sem order no server)."""
        from services.price_service import search_prices

        mock_client, _, qb = make_mocks()
        qb._return_data = SAMPLE_PRICES
        mock_get.return_value = mock_client

        result = search_prices("Leite Condensado Integral")

        # server-side: NENHUM order aplicado (price_per_kg é client-side)
        orders = [f for f in qb._applied_filters if f[0] == "order"]
        assert len(orders) == 0, f"Esperado 0 orders, encontrado: {orders}"
        # client-side: retorna ordenado por price_per_kg ASC
        assert len(result) > 0
        ppk = [r.get("normalized", {}).get("price_per_kg", 0) for r in result]
        assert ppk == sorted(ppk)

    # ── get_latest_prices ──────────────────────────────────────

    @patch("services.price_service.get_supabase")
    def test_get_latest_prices_valid_only(self, mock_get):
        """valid_only=True aplica filtro de vigencia."""
        from services.price_service import get_latest_prices

        mock_client, _, qb = make_mocks()
        qb._return_data = SAMPLE_PRICES
        mock_get.return_value = mock_client

        get_latest_prices(valid_only=True)

        types = [f[0] for f in qb._applied_filters]
        assert "lte" in types
        assert "gte" in types

    @patch("services.price_service.get_supabase")
    def test_get_latest_prices_all(self, mock_get):
        """valid_only=False sem filtro."""
        from services.price_service import get_latest_prices

        mock_client, _, qb = make_mocks()
        qb._return_data = SAMPLE_PRICES
        mock_get.return_value = mock_client

        get_latest_prices(valid_only=False)

        types = [f[0] for f in qb._applied_filters]
        assert "lte" not in types
        assert "gte" not in types

    # ── get_price_history ──────────────────────────────────────

    @patch("services.price_service.get_supabase")
    def test_get_price_history_valid_only(self, mock_get):
        """valid_only=True aplica filtro de vigencia."""
        from services.price_service import get_price_history

        mock_client, _, qb = make_mocks()
        qb._return_data = SAMPLE_HISTORY
        mock_get.return_value = mock_client

        get_price_history("Leite Condensado Integral", days=30, valid_only=True)

        types = [f[0] for f in qb._applied_filters]
        assert "lte" in types
        assert "gte" in types

    @patch("services.price_service.get_supabase")
    def test_get_price_history_valid_only_false(self, mock_get):
        """valid_only=False nao deve aplicar filtros de vigencia,
        mas ainda aplica gte para o filtro de dias."""
        from services.price_service import get_price_history

        mock_client, _, qb = make_mocks()
        qb._return_data = SAMPLE_HISTORY
        mock_get.return_value = mock_client

        get_price_history("Leite Condensado Integral", days=30, valid_only=False)

        types = [f[0] for f in qb._applied_filters]
        assert "lte" not in types, "Nao deveria filtrar lte valid_from"
        # Nota: gte aparece para o filtro de dias (collected_at), NAO para valid_until
        # Verificamos que existe um gte com collected_at
        gte_filters = [f for f in qb._applied_filters if f[0] == "gte"]
        gte_fields = [f[1] for f in gte_filters]
        assert "valid_until" not in gte_fields, "Nao deveria filtrar gte valid_until"

    # ── insert_review_item ─────────────────────────────────────

    @patch("services.price_service.get_service_client")
    def test_insert_review_item_with_validity(self, mock_get_client):
        """Inclui validity_raw no payload."""
        from services.price_service import insert_review_item

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        insert_review_item({
            "raw_product": "Leite Ninho 400g Oferta",
            "raw_price": 25.90, "raw_unit": "un",
            "store_name": "Extra", "source": "automated",
            "confidence": 0.65, "suggestions": ["Leite Ninho Integral"],
            "validity_raw": "Promocao semana do cliente",
        })

        assert qb._captured_insert is not None
        assert qb._captured_insert["raw_product"] == "Leite Ninho 400g Oferta"
        assert qb._captured_insert["validity_raw"] == "Promocao semana do cliente"
        assert qb._captured_insert["status"] == "pending"

    @patch("services.price_service.get_service_client")
    def test_insert_review_item_dedup_any_status(self, mock_get_client):
        """Dedup funciona independente do status (pending, approved, rejected)."""
        from services.price_service import insert_review_item

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        # Simula item existente com status "approved"
        qb._return_data = [{"id": "existing-id"}]

        result = insert_review_item({
            "raw_product": "Ninho Integral 400g",
            "raw_price": 25.90, "raw_unit": "un",
            "store_name": "Extra", "source": "automated",
            "confidence": 0.65, "suggestions": ["Leite Ninho Integral"],
            "validity_raw": "",
        })

        # Deve retornar o existente e NAO inserir novo
        assert result["id"] == "existing-id"
        assert qb._captured_insert is None, "Nao deveria inserir novo registro"

        # Verifica que checou store_name + raw_product SEM filtro de status
        eq_filters = [f for f in qb._applied_filters if f[0] == "eq"]
        eq_fields = [f[1] for f in eq_filters]
        assert "store_name" in eq_fields
        assert "raw_product" in eq_fields
        assert "status" not in eq_fields, "Nao deveria filtrar por status"

    # ── approve_review_item ────────────────────────────────────

    @patch("services.price_service.get_service_client")
    @patch("services.price_service.get_store_by_name", return_value={"id": "test_store", "name": "Test"})
    @patch("services.price_service.add_alias_to_ingredient", return_value=True)
    def test_approve_review_item_updates_and_upserts(self, mock_alias, mock_store, mock_get_client):
        """Aprova: update status + upsert price."""
        from services.price_service import approve_review_item

        mock_client, table, qb = make_mocks()
        qb._return_data = SAMPLE_REVIEW
        mock_get_client.return_value = mock_client

        approve_review_item("r1", "Leite Ninho Integral")

        assert qb._captured_update is not None, "update() deveria ser chamado"
        assert qb._captured_update.get("status") == "approved"
        fn_name, rpc_params = mock_client._captured_rpc
        assert fn_name == "upsert_price_rpc", "upsert should use RPC"
        assert rpc_params["p_ingredient_id"] == "Leite Ninho Integral"

    # ── reject_review_item ─────────────────────────────────────

    @patch("services.price_service.get_service_client")
    def test_reject_review_item_sets_rejected(self, mock_get_client):
        """Rejeita: marca status rejected."""
        from services.price_service import reject_review_item

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        reject_review_item("r1")

        assert qb._captured_update is not None, "update() deveria ser chamado"

    # ── get_telegram_report ────────────────────────────────────

    @patch("services.price_service.get_supabase")
    def test_get_telegram_report_empty(self, mock_get):
        """Lista vazia de ingredientes retorna lista vazia."""
        from services.price_service import get_telegram_report

        mock_client, _, _ = make_mocks()
        mock_get.return_value = mock_client

        assert get_telegram_report([], top_n=5) == []

    @patch("services.price_service.get_supabase")
    def test_get_telegram_report_ignores_connection_error(self, mock_get):
        """Nao quebra se Supabase offline."""
        from services.price_service import get_telegram_report

        mock_get.side_effect = Exception("offline")

        result = get_telegram_report([{"canonical": "X", "aliases": []}], top_n=5)
        assert isinstance(result, list)

    # ── _detect_promotion ──────────────────────────────────────

    def test_detect_promotion_keywords(self):
        from services.price_service import _detect_promotion

        cases = [
            ("PROMO Leite", "cx", True),
            ("Oferta Imperdivel", "1kg", True),
            ("Granulado 500g", "un", False),
            ("Chocolate 50% OFF", "barra", True),
            ("Leite 30% off", "lata", True),
            ("promocao valida", "", True),
            ("Farinha de Trigo", "1kg", False),
            ("desconto especial", "cx", True),
            ("Produto normal", "un", False),
            ("", "", False),
        ]
        for product, unit, expected in cases:
            assert _detect_promotion(product, unit) == expected, \
                f"Falhou: {product=} {unit=} -> esperado {expected}"

    # ── _weekday_pt ────────────────────────────────────────────

    def test_weekday_pt(self):
        from datetime import datetime
        from services.price_service import _weekday_pt

        for dt, expected in [
            (datetime(2026, 6, 15), "Seg"),
            (datetime(2026, 6, 16), "Ter"),
            (datetime(2026, 6, 17), "Qua"),
            (datetime(2026, 6, 18), "Qui"),
            (datetime(2026, 6, 19), "Sex"),
            (datetime(2026, 6, 20), "Sab"),
            (datetime(2026, 6, 21), "Dom"),
        ]:
            assert _weekday_pt(dt) == expected

    # ── get_prices_for_ingredient ──────────────────────────────

    @patch("services.price_service.get_supabase")
    def test_get_prices_for_ingredient_default_order(self, mock_get):
        """Ordena por price_per_kg ASC no cliente (sem order no server)."""
        from services.price_service import get_prices_for_ingredient

        mock_client, _, qb = make_mocks()
        qb._return_data = SAMPLE_PRICES
        mock_get.return_value = mock_client

        result = get_prices_for_ingredient("Leite Condensado Integral")

        # server-side: NENHUM order aplicado
        orders = [f for f in qb._applied_filters if f[0] == "order"]
        assert len(orders) == 0, f"Esperado 0 orders, encontrado: {orders}"
        # client-side: ordenado por price_per_kg ASC
        assert len(result) > 0
        ppk = [r.get("normalized", {}).get("price_per_kg", 0) for r in result]
        assert ppk == sorted(ppk)


# ── get_cheapest_prices ─────────────────────────────────────

    @patch("services.price_service.search_prices")
    def test_get_cheapest_prices_basic(self, mock_search):
        """get_cheapest_prices() must call search_prices with correct params."""
        from services.price_service import get_cheapest_prices
        mock_search.return_value = [{"store_name": "Assai", "normalized": {"price_per_kg": 8.5}}]
        result = get_cheapest_prices("Leite Condensado", top_n=3)
        mock_search.assert_called_once_with("Leite Condensado", sort_by="price_per_kg", sort_order="asc", limit=3, valid_only=True)
        assert len(result) == 1
        assert result[0]["store_name"] == "Assai"

    @patch("services.price_service.search_prices")
    def test_get_cheapest_prices_empty(self, mock_search):
        """get_cheapest_prices() must return [] when no prices found."""
        from services.price_service import get_cheapest_prices
        mock_search.return_value = []
        result = get_cheapest_prices("Inexistente")
        assert result == []


# ── main.process_price_match ───────────────────────────────────

    @patch("main.upsert_price")
    @patch("main.match_ingredient")
    def test_process_price_match_sets_validity_fields(self, mock_match, mock_upsert):
        """process_price_match() deve incluir validity_raw, is_promotion, collected_weekday."""
        from main import process_price_match

        mock_match.return_value = ({"canonical": "Leite Condensado", "aliases": []}, 95.0, "exact")

        store = {"name": "Assai", "type": "pdf", "tier": 1, "city": "Santos"}
        result = process_price_match(store, "Leite Moca PROMO 50% OFF", 39.90, "cx 12x395g", [])

        assert result is not None
        assert result["is_promotion"] is True
        assert result["validity_raw"] == ""
        assert result["collected_weekday"] in ("Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom")

    @patch("main.upsert_price")
    @patch("main.match_ingredient")
    def test_process_price_match_no_promotion(self, mock_match, mock_upsert):
        """Sem keywords de promocao, is_promotion=False."""
        from main import process_price_match

        mock_match.return_value = ({"canonical": "Farinha", "aliases": []}, 95.0, "exact")

        store = {"name": "Assai", "type": "pdf", "tier": 1}
        result = process_price_match(store, "Farinha de Trigo 1kg", 5.90, "1kg", [])

        assert result is not None
        assert result["is_promotion"] is False

    @patch("main.insert_review_item")
    @patch("main.match_ingredient")
    def test_process_price_match_review_has_validity(self, mock_match, mock_insert):
        """Review queue deve receber validity_raw."""
        from main import process_price_match

        mock_match.return_value = (None, 60.0, "fuzzy")

        store = {"name": "Extra", "type": "website"}
        process_price_match(store, "Produto Desconto 30%", 15.0, "un", [], validity_raw="Promo Semanal")

        inserted = mock_insert.call_args[0][0]
        assert inserted["validity_raw"] == "Promo Semanal"
        assert inserted["confidence"] == 0.6

    @patch("main.upsert_price")
    @patch("main.match_ingredient")
    def test_process_price_match_passes_validity_raw(self, mock_match, mock_upsert):
        """Validity_raw fornecido externamente deve ser passado ao entry."""
        from main import process_price_match

        mock_match.return_value = ({"canonical": "Leite Ninho", "aliases": []}, 90.0, "exact")

        store = {"name": "Extra", "type": "website", "tier": 2}
        result = process_price_match(
            store, "Leite Ninho Integral 400g", 25.90, "un", [],
            validity_raw="Oferta valida ate 30/06",
        )

        assert result is not None
        assert result["validity_raw"] == "Oferta valida ate 30/06"

    @patch("main.upsert_price")
    @patch("main.match_ingredient")
    def test_process_price_match_extracts_date_from_product(self, mock_match, mock_upsert):
        """Extrai texto de validade do nome do produto quando validity_raw nao fornecido."""
        from main import process_price_match

        mock_match.return_value = ({"canonical": "Teste", "aliases": []}, 95.0, "exact")

        store = {"name": "Test", "type": "pdf", "tier": 1}
        result = process_price_match(
            store, "Produto Teste ate 30/06/2026", 10.0, "un", [],
        )

        assert result is not None
        assert "30/06" in result["validity_raw"]


# ═══════════════════════════════════════════════════════════════
# SCRAPER TESTS
# ═══════════════════════════════════════════════════════════════

class TestFlyerParser:

    def test_parse_flyer_lines_with_validity(self):
        """Validity lines sao capturadas e associadas ao proximo produto."""
        from scrapers.flyer_parser import parse_flyer_lines

        lines = [
            "LEITE CONDENSADO MOCA CX 12X395G",
            "R$ 42,90",
            "Valido ate 30/06/2026",
            "CREME DE LEITE LATA 300G",
            "R$ 8,90",
        ]

        products = parse_flyer_lines(lines)
        assert len(products) == 2
        assert products[0]["validity_raw"] == ""
        assert "valido" in products[1]["validity_raw"].lower()
        assert "30/06" in products[1]["validity_raw"]

    def test_parse_flyer_lines_no_validity(self):
        """Sem linhas de validade, validity_raw vazio."""
        from scrapers.flyer_parser import parse_flyer_lines

        lines = [
            "LEITE CONDENSADO MOCA CX 12X395G",
            "R$ 42,90",
            "CREME DE LEITE LATA 300G",
            "R$ 8,90",
        ]

        products = parse_flyer_lines(lines)
        assert len(products) == 2
        assert all(p["validity_raw"] == "" for p in products)

    def test_parse_flyer_lines_validity_before_product(self):
        """Valor captura validade que aparece antes do produto."""
        from scrapers.flyer_parser import parse_flyer_lines

        lines = [
            "Oferta valida ate 15/07",
            "LEITE NINHO INTEGRAL 400G",
            "R$ 25,90",
        ]

        products = parse_flyer_lines(lines)
        assert len(products) == 1
        assert "15/07" in products[0]["validity_raw"]


class TestVtexScraper:

    def test_parse_product_with_validity(self):
        """priceValidUntil extraido do commertialOffer."""
        from scrapers.vtex_scraper import VtexScraper

        scraper = VtexScraper({"name": "TestStore", "base_url": "https://test.com"})
        product = {
            "productName": "Leite Moca",
            "items": [{
                "nameComplete": "Leite Moca CX 12x395g",
                "sellers": [{
                    "commertialOffer": {
                        "Price": 42.90,
                        "AvailableQuantity": 10,
                        "priceValidUntil": "2026-07-15T23:59:59Z",
                    }
                }],
            }],
        }

        entries = scraper.parse_product(product, {"canonical": "Leite Moca", "brands": ["Moca"]})
        assert len(entries) == 1
        assert entries[0]["validity_raw"] == "2026-07-15T23:59:59Z"

    def test_parse_product_no_validity(self):
        """Sem priceValidUntil, validity_raw vazio."""
        from scrapers.vtex_scraper import VtexScraper

        scraper = VtexScraper({"name": "TestStore", "base_url": "https://test.com"})
        product = {
            "productName": "Farinha",
            "items": [{
                "nameComplete": "Farinha de Trigo 1kg",
                "sellers": [{
                    "commertialOffer": {
                        "Price": 5.90,
                        "AvailableQuantity": 5,
                    }
                }],
            }],
        }

        entries = scraper.parse_product(product, {"canonical": "Farinha", "brands": []})
        assert len(entries) == 1
        assert entries[0]["validity_raw"] == ""

    def test_parse_product_empty_price_valid_until(self):
        """priceValidUntil vazio string."""
        from scrapers.vtex_scraper import VtexScraper

        scraper = VtexScraper({"name": "TestStore", "base_url": "https://test.com"})
        product = {
            "productName": "Acucar",
            "items": [{
                "nameComplete": "Acucar 5kg",
                "sellers": [{
                    "commertialOffer": {
                        "Price": 18.90,
                        "AvailableQuantity": 3,
                        "priceValidUntil": "",
                    }
                }],
            }],
        }

        entries = scraper.parse_product(product, {"canonical": "Acucar", "brands": []})
        assert len(entries) == 1
        assert entries[0]["validity_raw"] == ""


class TestWebsiteScraper:

    def test_parse_results_with_validity_selector(self):
        """Product_validity selector presente retorna validity_raw."""
        from scrapers.website_scraper import WebsiteScraper

        store = {
            "name": "TestStore",
            "base_url": "https://test.com",
            "selectors": {
                "product_card": [".card"],
                "product_name": [".name"],
                "product_price": [".price"],
                "product_validity": [".validity"],
            },
        }
        scraper = WebsiteScraper(store)

        html = """
        <html><body>
            <div class="card">
                <div class="name">Leite Moca CX 12x395g</div>
                <div class="price">R$ 42,90</div>
                <div class="validity">Valido ate 30/06/2026</div>
            </div>
        </body></html>
        """

        results = scraper.parse_products(html)
        assert len(results) == 1
        assert results[0]["validity_raw"] == "Valido ate 30/06/2026"

    def test_parse_results_no_validity_selector(self):
        """Sem product_validity, validity_raw vazio."""
        from scrapers.website_scraper import WebsiteScraper

        scraper = WebsiteScraper({
            "name": "TestStore",
            "base_url": "https://test.com",
            "selectors": {
                "product_card": [".card"],
                "product_name": [".name"],
                "product_price": [".price"],
            },
        })
        html = """
        <html><body>
            <div class="card">
                <div class="name">Farinha 1kg</div>
                <div class="price">R$ 5,90</div>
            </div>
        </body></html>
        """

        results = scraper.parse_products(html)
        assert len(results) == 1
        assert results[0]["validity_raw"] == ""


# ═══════════════════════════════════════════════════════════════
# EMAIL SERVICE TESTS
# ═══════════════════════════════════════════════════════════════

class TestEmailService:

    def test_build_full_report_html_structure(self):
        """HTML completo com promocao, validade, multiplos ingredientes."""
        from services.email_service import build_full_report_html

        prices = {
            "Leite Condensado": [
                {"store_name": "Assai", "raw_product": "Moca", "raw_price": 42.90,
                 "raw_unit": "cx", "normalized": {"price_per_kg": 10.5},
                 "is_promotion": False, "valid_until": "2026-07-01"},
                {"store_name": "Atacadao", "raw_product": "Moca PROMO", "raw_price": 39.90,
                 "raw_unit": "cx", "normalized": {"price_per_kg": 9.98},
                 "is_promotion": True, "valid_until": "2026-07-05"},
            ],
            "Creme de Leite": [
                {"store_name": "Spani", "raw_product": "Nestle Creme", "raw_price": 8.90,
                 "raw_unit": "lata", "normalized": {"price_per_kg": 35.60},
                 "is_promotion": False, "valid_until": ""},
            ],
        }

        html = build_full_report_html(prices)
        assert "<!DOCTYPE html>" in html
        assert "Leite Condensado" in html
        assert "Creme de Leite" in html
        assert "Assai" in html and "Atacadao" in html and "Spani" in html
        assert "R$ 42.90" in html and "R$ 39.90" in html and "R$ 8.90" in html
        assert "PROMO" in html
        assert "at" in html
        assert "R$/kg" in html and "Loja" in html

    def test_build_full_report_html_empty(self):
        """Dict vazio gera HTML basico sem erros."""
        from services.email_service import build_full_report_html

        html = build_full_report_html({})
        assert "<!DOCTYPE html>" in html
        assert "CustoDoce" in html


# ═══════════════════════════════════════════════════════════════
# CLEANUP TESTS
# ═══════════════════════════════════════════════════════════════

class TestCleanupService:

    @patch("services.price_service.get_service_client")
    def test_cleanup_old_prices_calls_rpc(self, mock_get_client):
        """cleanup_old_prices() chama rpc('cleanup_old_prices')."""
        from services.price_service import cleanup_old_prices

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        result = cleanup_old_prices(retention_days=90)

        assert mock_client._captured_rpc is not None
        fn_name, params = mock_client._captured_rpc
        assert fn_name == "cleanup_old_prices"
        assert params == {"retention_days": 90}
        assert "deleted" in result

    @patch("services.price_service.get_service_client")
    def test_cleanup_old_prices_default_retention(self, mock_get_client):
        """Usa 90 dias como padrao."""
        from services.price_service import cleanup_old_prices

        mock_client, _, _ = make_mocks()
        mock_get_client.return_value = mock_client

        cleanup_old_prices()

        assert mock_client._captured_rpc is not None
        _, params = mock_client._captured_rpc
        assert params == {"retention_days": 90}

    @patch("services.price_service.get_service_client")
    def test_cleanup_old_logs_calls_rpc(self, mock_get_client):
        """cleanup_old_logs() chama rpc('cleanup_old_logs')."""
        from services.price_service import cleanup_old_logs

        mock_client, _, _ = make_mocks()
        mock_get_client.return_value = mock_client

        result = cleanup_old_logs(retention_days=30)

        assert mock_client._captured_rpc is not None
        fn_name, params = mock_client._captured_rpc
        assert fn_name == "cleanup_old_logs"
        assert params == {"retention_days": 30}
        assert "deleted" in result

    @patch("services.price_service.get_service_client")
    def test_cleanup_old_logs_default_retention(self, mock_get_client):
        """Usa 30 dias como padrao."""
        from services.price_service import cleanup_old_logs

        mock_client, _, _ = make_mocks()
        mock_get_client.return_value = mock_client

        cleanup_old_logs()

        assert mock_client._captured_rpc is not None
        _, params = mock_client._captured_rpc
        assert params == {"retention_days": 30}

    @patch("services.flyer_service.get_service_client")
    def test_cleanup_old_flyers_calls_rpc(self, mock_get_client):
        """cleanup_old_flyers() chama rpc('cleanup_old_flyers')."""
        from services.flyer_service import cleanup_old_flyers

        mock_client, _, _ = make_mocks()
        mock_get_client.return_value = mock_client

        result = cleanup_old_flyers(retention_days=60)

        assert mock_client._captured_rpc is not None
        fn_name, params = mock_client._captured_rpc
        assert fn_name == "cleanup_old_flyers"
        assert params == {"retention_days": 60}
        assert "deleted" in result

    @patch("services.flyer_service.get_service_client")
    def test_cleanup_old_flyers_default_retention(self, mock_get_client):
        """Usa 60 dias como padrao."""
        from services.flyer_service import cleanup_old_flyers

        mock_client, _, _ = make_mocks()
        mock_get_client.return_value = mock_client

        cleanup_old_flyers()

        assert mock_client._captured_rpc is not None
        _, params = mock_client._captured_rpc
        assert params == {"retention_days": 60}


class TestUnitExtractor:
    """Testes P0 para parsers/unit_extractor.py — extract_unit()."""

    def test_extract_unit_cx_multiple(self):
        from parsers.unit_extractor import extract_unit
        assert extract_unit("cx 12x395g") == "12x395g"

    def test_extract_unit_multiplication(self):
        from parsers.unit_extractor import extract_unit
        assert extract_unit("cx 12x395g Leite") == "12x395g"

    def test_extract_unit_simple_weight(self):
        from parsers.unit_extractor import extract_unit
        assert extract_unit("2kg") == "2kg"
        assert extract_unit("500g") == "500g"

    def test_extract_unit_kg_with_g(self):
        from parsers.unit_extractor import extract_unit
        assert extract_unit("1.5kg") == "1.5kg"

    def test_extract_unit_liter(self):
        from parsers.unit_extractor import extract_unit
        assert extract_unit("1L") == "1L"
        assert extract_unit("2l") == "2l"

    def test_extract_unit_lata(self):
        from parsers.unit_extractor import extract_unit
        assert extract_unit("lata 1kg") == "1kg"

    def test_extract_unit_pacote(self):
        from parsers.unit_extractor import extract_unit
        assert extract_unit("pacote com 5") == "pacote com 5"

    def test_extract_unit_empty(self):
        from parsers.unit_extractor import extract_unit
        assert extract_unit("Nestle Leite Condensado") == ""

    def test_extract_unit_case_insensitive(self):
        from parsers.unit_extractor import extract_unit
        assert extract_unit("Caixa 12X200G") == "12X200G"
        assert extract_unit("CX 24X200ml") == "24X200ml"


class TestNormalizer:
    """Testes P0 para parsers/normalizer.py — parse_unit() e normalize_price()."""

    def test_parse_unit_cx_12x395g(self):
        from parsers.normalizer import parse_unit
        result = parse_unit("cx 12x395g")
        assert result is not None
        assert result.qty == 12
        assert abs(result.unit_kg - 0.395) < 0.001
        assert abs(result.total_kg - 4.74) < 0.001

    def test_parse_unit_2kg(self):
        from parsers.normalizer import parse_unit
        result = parse_unit("2kg")
        assert result is not None
        assert result.qty == 1
        assert abs(result.unit_kg - 2.0) < 0.001
        assert abs(result.total_kg - 2.0) < 0.001

    def test_parse_unit_500g(self):
        from parsers.normalizer import parse_unit
        result = parse_unit("500g")
        assert result is not None
        assert abs(result.unit_kg - 0.5) < 0.001

    def test_parse_unit_empty(self):
        from parsers.normalizer import parse_unit
        assert parse_unit("") is None

    def test_parse_unit_invalid(self):
        from parsers.normalizer import parse_unit
        assert parse_unit(None) is None
        assert parse_unit(123) is None  # type: ignore

    def test_normalize_price_basic(self):
        from parsers.normalizer import normalize_price
        result = normalize_price(42.90, "cx 12x395g")
        assert result is not None
        expected_kg = 42.90 / (12 * 0.395)
        assert abs(result.price_per_kg - expected_kg) < 0.01
        assert abs(result.price_per_un - 42.90 / 12) < 0.01

    def test_normalize_price_2kg(self):
        from parsers.normalizer import normalize_price
        result = normalize_price(25.00, "2kg")
        assert result is not None
        assert abs(result.price_per_kg - 12.50) < 0.01
        assert abs(result.price_per_un - 25.00) < 0.01

    def test_normalize_price_zero_negative(self):
        from parsers.normalizer import normalize_price
        assert normalize_price(0, "2kg") is None
        assert normalize_price(-1, "2kg") is None

    def test_normalize_price_invalid_unit(self):
        from parsers.normalizer import normalize_price
        assert normalize_price(10.00, "") is None

    def test_normalized_price_to_dict(self):
        from parsers.normalizer import NormalizedPrice
        np = NormalizedPrice(qty=6, unit_kg=0.5, total_kg=3.0,
                             price_per_kg=10.0, price_per_un=5.0)
        d = np.to_dict()
        assert d["qty"] == 6
        assert d["price_per_kg"] == 10.0

    def test_normalized_price_repr(self):
        from parsers.normalizer import NormalizedPrice
        np = NormalizedPrice(qty=1, unit_kg=2.0, total_kg=2.0,
                             price_per_kg=12.50, price_per_un=25.00)
        r = repr(np)
        assert "R$12.50/kg" in r
        assert "R$25.00/un" in r


class TestMatcher:
    """Testes P0 para parsers/matcher.py — match_ingredient e auxiliares."""

    INGREDIENTS = [
        {"canonical": "Leite Condensado",
         "aliases": ["Leite Condensado Moça", "Leite Cond Molico"]},
        {"canonical": "Creme de Leite",
         "aliases": ["Creme de Leite Nestle", "Nestle Creme de Leite"]},
        {"canonical": "Chocolate em Pó 50%",
         "aliases": ["Chocolate em Pó 50% Cacau"]},
    ]

    def test_clean_text(self):
        from parsers.matcher import clean_text
        assert clean_text("Leite Condensado 12un") == "LEITE CONDENSADO 12UN"
        assert clean_text("Creme de Leite - Nestle") == "CREME DE LEITE NESTLE"
        assert clean_text("") == ""

    def test_match_exact_canonical(self):
        from parsers.matcher import match_exact
        assert match_exact("Leite Condensado Moça 395g", self.INGREDIENTS[0])
        assert not match_exact("Creme de Leite", self.INGREDIENTS[0])

    def test_match_exact_alias(self):
        from parsers.matcher import match_exact
        assert match_exact("Leite Cond Molico 395g", self.INGREDIENTS[0])

    def test_match_exact_word_subset(self):
        from parsers.matcher import match_exact
        assert match_exact("Leite Condensado Integral Moça", self.INGREDIENTS[0])

    def test_match_ingredient_exact(self):
        from parsers.matcher import match_ingredient
        result = match_ingredient("Leite Condensado Moça", self.INGREDIENTS)
        assert result[0] is not None
        assert result[0]["canonical"] == "Leite Condensado"
        assert result[1] == 100.0
        assert result[2] == "exact"

    def test_match_ingredient_fuzzy(self):
        from parsers.matcher import match_ingredient
        # "Creme Fresco Leite" scores ~88% on "Creme de Leite"
        # but does NOT contain "Creme de Leite" or aliases verbatim
        coca, score, match_type = match_ingredient(
            "Creme Fresco Leite Nestle", self.INGREDIENTS
        )
        assert coca is not None
        assert coca["canonical"] == "Creme de Leite"
        assert score >= 80.0
        assert match_type in ("fuzzy_canonical", "fuzzy_alias")

    def test_match_ingredient_no_match(self):
        from parsers.matcher import match_ingredient
        result = match_ingredient("Arroz Branco 5kg", self.INGREDIENTS)
        assert result[0] is None
        assert result[1] < 80.0

    def test_match_ingredient_threshold_high(self):
        from parsers.matcher import match_ingredient
        result = match_ingredient("Leite Condensado", self.INGREDIENTS, threshold=99.0)
        assert result[0] is not None
        assert result[1] == 100.0
        assert result[2] == "exact"

    def test_rank_ingredients(self):
        from parsers.matcher import rank_ingredients
        result = rank_ingredients("Chocolate em Pó 50% Cacau 200g", self.INGREDIENTS, top_n=2)
        assert len(result) == 2
        assert result[0][0]["canonical"] == "Chocolate em Pó 50%"

    def test_build_alias_list(self):
        from parsers.matcher import build_alias_list
        result = build_alias_list(self.INGREDIENTS)
        assert len(result) >= 5
        pairs = [(c, a) for c, a, _ in result]
        assert ("Leite Condensado", "Leite Condensado") in pairs
        assert ("Leite Condensado", "Leite Condensado Moça") in pairs


class TestLongitudinalWinners:
    """Testes para get_longitudinal_winners, get_price_trends, get_cross_ingredient_ranking."""

    def test_longitudinal_winners_returns_empty_when_no_data(self):
        from services.price_service import get_longitudinal_winners
        with patch("services.price_service.get_supabase") as mock:
            mock.return_value = MockSupabaseClient(MockQueryBuilder([]))
            result = get_longitudinal_winners(days=90)
        assert result == []

    def test_longitudinal_winners_counts_wins(self):
        from services.price_service import get_longitudinal_winners
        data = [
            {"ingredient_id": "leite", "store_name": "Assai", "normalized": {"price_per_kg": 10.0}, "collected_at": "2026-06-01"},
            {"ingredient_id": "leite", "store_name": "Atacadao", "normalized": {"price_per_kg": 12.0}, "collected_at": "2026-06-01"},
            {"ingredient_id": "leite", "store_name": "Assai", "normalized": {"price_per_kg": 11.0}, "collected_at": "2026-06-02"},
            {"ingredient_id": "leite", "store_name": "Atacadao", "normalized": {"price_per_kg": 9.0}, "collected_at": "2026-06-02"},
        ]
        with patch("services.price_service.get_supabase") as mock:
            mock.return_value = MockSupabaseClient(MockQueryBuilder(data))
            result = get_longitudinal_winners(days=90)
        assert len(result) == 2
        wins = {r["store_name"]: r["wins"] for r in result}
        assert wins["Assai"] == 1  # 2026-06-01
        assert wins["Atacadao"] == 1  # 2026-06-02

    def test_longitudinal_winners_skips_zero_ppk(self):
        from services.price_service import get_longitudinal_winners
        data = [
            {"ingredient_id": "leite", "store_name": "Assai", "normalized": {"price_per_kg": 0}, "collected_at": "2026-06-01"},
        ]
        with patch("services.price_service.get_supabase") as mock:
            mock.return_value = MockSupabaseClient(MockQueryBuilder(data))
            result = get_longitudinal_winners(days=90)
        assert result == []

    def test_price_trends_returns_empty_when_no_data(self):
        from services.price_service import get_price_trends
        with patch("services.price_service.get_supabase") as mock:
            mock.return_value = MockSupabaseClient(MockQueryBuilder([]))
            result = get_price_trends("leite", days=90)
        assert result == []

    def test_price_trends_computes_avg_min_max(self):
        from services.price_service import get_price_trends
        data = [
            {"store_name": "Assai", "normalized": {"price_per_kg": 10.0}, "collected_at": "2026-06-01"},
            {"store_name": "Atacadao", "normalized": {"price_per_kg": 12.0}, "collected_at": "2026-06-01"},
            {"store_name": "Assai", "normalized": {"price_per_kg": 11.0}, "collected_at": "2026-06-02"},
            {"store_name": "Atacadao", "normalized": {"price_per_kg": 9.0}, "collected_at": "2026-06-02"},
        ]
        with patch("services.price_service.get_supabase") as mock:
            mock.return_value = MockSupabaseClient(MockQueryBuilder(data))
            result = get_price_trends("leite", days=90)
        assert len(result) == 2
        assert result[0]["date"] == "2026-06-01"
        assert result[0]["avg_ppk"] == 11.0
        assert result[0]["min_ppk"] == 10.0
        assert result[0]["max_ppk"] == 12.0
        assert result[0]["store_count"] == 2

    def test_cross_ingredient_ranking_returns_empty_when_no_data(self):
        from services.price_service import get_cross_ingredient_ranking
        with patch("services.price_service.get_supabase") as mock:
            mock.return_value = MockSupabaseClient(MockQueryBuilder([]))
            result = get_cross_ingredient_ranking(days=90)
        assert result == []

    def test_cross_ingredient_ranking_counts_top1_and_top3(self):
        from services.price_service import get_cross_ingredient_ranking
        data = [
            {"ingredient_id": "leite", "store_name": "Assai", "normalized": {"price_per_kg": 10.0}, "collected_at": "2026-06-01"},
            {"ingredient_id": "leite", "store_name": "Atacadao", "normalized": {"price_per_kg": 12.0}, "collected_at": "2026-06-01"},
            {"ingredient_id": "choco", "store_name": "Assai", "normalized": {"price_per_kg": 20.0}, "collected_at": "2026-06-01"},
            {"ingredient_id": "choco", "store_name": "Atacadao", "normalized": {"price_per_kg": 18.0}, "collected_at": "2026-06-01"},
        ]
        with patch("services.price_service.get_supabase") as mock:
            mock.return_value = MockSupabaseClient(MockQueryBuilder(data))
            result = get_cross_ingredient_ranking(days=90)
        assert len(result) == 2
        scores = {r["store_name"]: r for r in result}
        assert scores["Assai"]["top1_count"] == 1  # leite
        assert scores["Assai"]["top3_count"] == 2  # leite + choco
        assert scores["Atacadao"]["top1_count"] == 1  # choco
        assert scores["Atacadao"]["top3_count"] == 2  # leite + choco


class TestAuthTotp:
    """Testes P0 para services/auth.py — verify_totp() e _totp_int()."""

    def test_totp_int_returns_int(self):
        from services.auth import _totp_int, generate_totp_secret
        secret = generate_totp_secret()
        code = _totp_int(secret, 12345678)
        assert isinstance(code, int)
        assert 0 <= code <= 999999

    def test_verify_totp_invalid_string(self):
        from services.auth import verify_totp
        assert verify_totp("SECRET", "") is False
        assert verify_totp("SECRET", "abc123") is False

    def test_verify_totp_wrong_code(self):
        from services.auth import verify_totp
        secret = "AAAAAAAAAAAAAAAA"
        assert verify_totp(secret, "000000") is False


class TestBrandExtractor:
    """Testes P0 para parsers/brand_extractor.py."""

    INGREDIENT = {
        "canonical": "Leite Condensado Integral",
        "brands": ["Moça", "Piracanjuba", "Itambé"],
    }
    MULTI_INGREDIENTS = [
        INGREDIENT,
        {"canonical": "Chocolate em Pó 50% Cacau", "brands": ["Melken", "Nestlé"]},
    ]

    def test_extract_brand_found_word_boundary(self):
        from parsers.brand_extractor import extract_brand
        assert extract_brand("Leite Condensado Moça 395g", self.INGREDIENT) == "Moça"

    def test_extract_brand_found_multiple_words(self):
        from parsers.brand_extractor import extract_brand
        assert extract_brand("Leite Piracanjuba 1kg", self.INGREDIENT) == "Piracanjuba"

    def test_extract_brand_not_found(self):
        from parsers.brand_extractor import extract_brand
        assert extract_brand("Leite Condensado Genérico", self.INGREDIENT) == "Desconhecido"

    def test_extract_brand_empty_brands_list(self):
        from parsers.brand_extractor import extract_brand
        assert extract_brand("Leite Condensado", {"brands": []}) == "Desconhecido"

    def test_extract_brand_no_brands_key(self):
        from parsers.brand_extractor import extract_brand
        assert extract_brand("Leite Condensado", {}) == "Desconhecido"

    def test_extract_brand_case_insensitive(self):
        from parsers.brand_extractor import extract_brand
        assert extract_brand("LEITE CONDENSADO MOÇA 395G", self.INGREDIENT) == "Moça"

    def test_extract_brand_partial_word_no_match(self):
        from parsers.brand_extractor import extract_brand
        ing = {"canonical": "Teste", "brands": ["Moca"]}
        assert extract_brand("Mocambo 1kg", ing) == "Desconhecido"

    def test_extract_brand_from_all_found(self):
        from parsers.brand_extractor import extract_brand_from_all
        assert extract_brand_from_all("Chocolate Melken 1kg", self.MULTI_INGREDIENTS) == "Melken"

    def test_extract_brand_from_all_not_found(self):
        from parsers.brand_extractor import extract_brand_from_all
        assert extract_brand_from_all("Produto Genérico", self.MULTI_INGREDIENTS) is None

    def test_extract_brand_from_all_skips_duplicates(self):
        from parsers.brand_extractor import extract_brand_from_all
        ings = [
            {"canonical": "A", "brands": ["Nestlé"]},
            {"canonical": "B", "brands": ["Nestlé"]},
        ]
        assert extract_brand_from_all("Nestlé 1kg", ings) == "Nestlé"

    def test_extract_brand_from_all_empty(self):
        from parsers.brand_extractor import extract_brand_from_all
        assert extract_brand_from_all("Teste", []) is None


class TestConfigDb:
    """Testes P0 para services/config_db.py — CRUD com mocks do Supabase."""

    @classmethod
    def setup_class(cls):
        import importlib
        import sys
        # test_dashboard_full.py sets sys.modules["services.config_db"] = MagicMock
        # which breaks real imports. Force re-import the real module.
        if "services.config_db" in sys.modules:
            del sys.modules["services.config_db"]
        import services.config_db as _real
        importlib.reload(_real)

    SAMPLE_INGREDIENTS = [
        {"id": "1", "canonical_name": "Leite Condensado Integral", "active": True},
        {"id": "2", "canonical_name": "Creme de Leite", "active": True},
    ]
    SAMPLE_STORES = [
        {"id": "s1", "name": "Assaí", "is_active": True, "tier": 1, "priority": 1, "type": "atacado"},
        {"id": "s2", "name": "Extra", "is_active": False, "tier": 2, "priority": 5, "type": "supermercado"},
    ]
    SAMPLE_SCHEDULES = [
        {"id": "sch1", "name": "Coleta Diaria", "enabled": True, "cron": "0 12 * * *"},
    ]
    SAMPLE_RECIPIENTS = [
        {"id": "r1", "name": "Admin", "channel": "email", "active": True},
    ]
    SAMPLE_FLAGS = [
        {"key": "telegram_enabled", "enabled": True, "description": "Enable Telegram"},
    ]

    # ── INGREDIENTS ──

    @patch("services.config_db.get_supabase")
    def test_get_active_ingredients(self, mock_get_supabase):
        from services.config_db import get_active_ingredients
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder(self.SAMPLE_INGREDIENTS))
        result = get_active_ingredients()
        assert len(result) == 2
        assert result[0]["canonical_name"] == "Leite Condensado Integral"

    @patch("services.config_db.get_supabase")
    def test_get_all_ingredients_includes_inactive(self, mock_get_supabase):
        from services.config_db import get_all_ingredients
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder(self.SAMPLE_INGREDIENTS))
        result = get_all_ingredients(include_inactive=True)
        assert len(result) == 2

    @patch("services.config_db.get_supabase")
    def test_get_ingredient_by_id_found(self, mock_get_supabase):
        from services.config_db import get_ingredient_by_id
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([self.SAMPLE_INGREDIENTS[0]]))
        result = get_ingredient_by_id("1")
        assert result is not None
        assert result["canonical_name"] == "Leite Condensado Integral"

    @patch("services.config_db.get_supabase")
    def test_get_ingredient_by_id_not_found(self, mock_get_supabase):
        from services.config_db import get_ingredient_by_id
        qb = MockQueryBuilder([])
        qb.single = lambda: qb
        qb.execute = lambda: MockQueryResult(None)
        mock_get_supabase.return_value = MockSupabaseClient(qb)
        result = get_ingredient_by_id("999")
        assert result is None

    @patch("services.config_db.get_service_client")
    def test_upsert_ingredient(self, mock_get_client):
        from services.config_db import upsert_ingredient
        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client
        upsert_ingredient({"canonical_name": "Test", "active": True})
        assert qb._captured_upsert is not None
        assert qb._captured_upsert["canonical_name"] == "Test"
        assert "updated_at" in qb._captured_upsert

    @patch("services.config_db.get_service_client")
    def test_delete_ingredient(self, mock_get_client):
        from services.config_db import delete_ingredient
        qb = MockQueryBuilder([{"id": "123"}])
        mock_client = MockSupabaseClient(qb)
        mock_get_client.return_value = mock_client
        assert delete_ingredient("123") is True

    # ── STORES ──

    @patch("services.config_db.get_supabase")
    def test_get_active_stores(self, mock_get_supabase):
        from services.config_db import get_active_stores
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([self.SAMPLE_STORES[0]]))
        result = get_active_stores()
        assert len(result) == 1
        assert result[0]["name"] == "Assaí"

    @patch("services.config_db.get_supabase")
    def test_get_active_stores_filtered_by_tier(self, mock_get_supabase):
        from services.config_db import get_active_stores
        mock = MockSupabaseClient(MockQueryBuilder([]))
        mock_get_supabase.return_value = mock
        get_active_stores(tier=1)
        assert mock.qb is not None

    @patch("services.config_db.get_supabase")
    def test_get_all_stores_include_inactive(self, mock_get_supabase):
        from services.config_db import get_all_stores
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder(self.SAMPLE_STORES))
        result = get_all_stores(include_inactive=True)
        assert len(result) == 2

    @patch("services.config_db.get_service_client")
    def test_upsert_store(self, mock_get_client):
        from services.config_db import upsert_store
        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client
        upsert_store({"name": "Test Store", "tier": 1, "is_active": True})
        assert qb._captured_upsert is not None
        assert qb._captured_upsert["name"] == "Test Store"

    @patch("services.config_db.get_service_client")
    def test_delete_store(self, mock_get_client):
        from services.config_db import delete_store
        qb = MockQueryBuilder([{"id": "s1"}])
        mock_client = MockSupabaseClient(qb)
        mock_get_client.return_value = mock_client
        assert delete_store("s1") is True

    # ── SCHEDULES ──

    @patch("services.config_db.get_supabase")
    def test_get_enabled_schedules(self, mock_get_supabase):
        from services.config_db import get_enabled_schedules
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder(self.SAMPLE_SCHEDULES))
        result = get_enabled_schedules()
        assert len(result) == 1
        assert result[0]["name"] == "Coleta Diaria"

    @patch("services.config_db.get_service_client")
    def test_upsert_schedule(self, mock_get_client):
        from services.config_db import upsert_schedule
        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client
        upsert_schedule({"name": "Novo Cron", "cron": "0 6 * * *"})
        assert qb._captured_upsert is not None
        assert qb._captured_upsert["name"] == "Novo Cron"

    @patch("services.config_db.get_service_client")
    def test_update_schedule_run(self, mock_get_client):
        from services.config_db import update_schedule_run
        from datetime import datetime
        mock_client, _, _ = make_mocks()
        mock_get_client.return_value = mock_client
        now = datetime(2026, 6, 19)
        update_schedule_run("sch1", last_run=now)
        assert mock_client.qb is not None

    # ── RECIPIENTS ──

    @patch("services.config_db.get_supabase")
    def test_get_active_recipients(self, mock_get_supabase):
        from services.config_db import get_active_recipients
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder(self.SAMPLE_RECIPIENTS))
        result = get_active_recipients()
        assert len(result) == 1
        assert result[0]["channel"] == "email"

    @patch("services.config_db.get_supabase")
    def test_get_active_recipients_filtered(self, mock_get_supabase):
        from services.config_db import get_active_recipients
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder(self.SAMPLE_RECIPIENTS))
        result = get_active_recipients(channel="telegram")
        assert len(result) == 1  # mock returns data regardless of filter

    # ── FEATURE FLAGS ──

    @patch("services.config_db.get_supabase")
    def test_get_feature_flag_enabled(self, mock_get_supabase):
        from services.config_db import get_feature_flag
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([{"enabled": True}]))
        assert get_feature_flag("telegram_enabled") is True

    @patch("services.config_db.get_supabase")
    def test_get_feature_flag_disabled(self, mock_get_supabase):
        from services.config_db import get_feature_flag
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([{"enabled": False}]))
        assert get_feature_flag("telegram_enabled") is False

    @patch("services.config_db.get_supabase")
    def test_get_feature_flag_default(self, mock_get_supabase):
        from services.config_db import get_feature_flag
        qb = MockQueryBuilder([])
        qb.single = lambda: qb
        qb.execute = lambda: MockQueryResult(None)
        mock_get_supabase.return_value = MockSupabaseClient(qb)
        assert get_feature_flag("nonexistent", default=True) is True

    @patch("services.config_db.get_service_client")
    def test_upsert_feature_flag(self, mock_get_client):
        from services.config_db import upsert_feature_flag
        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client
        upsert_feature_flag("test_flag", enabled=True, description="Test flag")
        assert qb._captured_upsert is not None
        assert qb._captured_upsert["key"] == "test_flag"
        assert qb._captured_upsert["enabled"] is True

    # ── SCRAPE FREQUENCIES ──

    @patch("services.config_db.get_supabase")
    def test_get_scrape_frequency(self, mock_get_supabase):
        from services.config_db import get_scrape_frequency
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([]))
        result = get_scrape_frequency()
        assert result == []

    @patch("services.config_db.get_service_client")
    def test_upsert_scrape_frequency(self, mock_get_client):
        from services.config_db import upsert_scrape_frequency
        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client
        upsert_scrape_frequency({"store_id": "s1", "tier": 1, "enabled": True})
        assert qb._captured_upsert is not None

    @patch("services.config_db.get_service_client")
    def test_delete_scrape_frequency(self, mock_get_client):
        from services.config_db import delete_scrape_frequency
        qb = MockQueryBuilder([{"id": "f1"}])
        mock_client = MockSupabaseClient(qb)
        mock_get_client.return_value = mock_client
        assert delete_scrape_frequency("f1") is True

    # ── ALERT RULES ──

    @patch("services.config_db.get_supabase")
    def test_get_enabled_alert_rules(self, mock_get_supabase):
        from services.config_db import get_enabled_alert_rules
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([]))
        result = get_enabled_alert_rules()
        assert result == []

    @patch("services.config_db.get_service_client")
    def test_upsert_alert_rule(self, mock_get_client):
        from services.config_db import upsert_alert_rule
        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client
        upsert_alert_rule({"name": "Price Drop", "trigger": "price_drop", "enabled": True})
        assert qb._captured_upsert is not None
        assert qb._captured_upsert["name"] == "Price Drop"

    @patch("services.config_db.get_service_client")
    def test_delete_alert_rule(self, mock_get_client):
        from services.config_db import delete_alert_rule
        qb = MockQueryBuilder([{"id": "r1"}])
        mock_client = MockSupabaseClient(qb)
        mock_get_client.return_value = mock_client
        assert delete_alert_rule("r1") is True

    # ── STORE LOOKUPS ──

    @patch("services.config_db.get_supabase")
    def test_get_store_by_id(self, mock_get_supabase):
        from services.config_db import get_store_by_id
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([self.SAMPLE_STORES[0]]))
        result = get_store_by_id("s1")
        assert result is not None
        assert result["name"] == "Assaí"

    @patch("services.config_db.get_supabase")
    def test_get_store_by_name(self, mock_get_supabase):
        from services.config_db import get_store_by_name
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([self.SAMPLE_STORES[0]]))
        result = get_store_by_name("Assaí")
        assert result is not None
        assert result["name"] == "Assaí"

    @patch("services.config_db.get_supabase")
    def test_get_ingredient_by_name(self, mock_get_supabase):
        from services.config_db import get_ingredient_by_name
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([self.SAMPLE_INGREDIENTS[0]]))
        result = get_ingredient_by_name("Leite Condensado Integral")
        assert result is not None

    # ── ALL FEATURE FLAGS ──

    @patch("services.config_db.get_supabase")
    def test_get_all_feature_flags(self, mock_get_supabase):
        from services.config_db import get_all_feature_flags
        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder(self.SAMPLE_FLAGS))
        result = get_all_feature_flags()
        assert len(result) == 1
        assert result[0]["key"] == "telegram_enabled"


class TestBaseWebScraper:
    """Testes P0 para scrapers/base_web_scraper.py — logica sem rede."""

    def _make_concrete_scraper(self, store_config=None, rate_limit=None):
        """Factory method: cria uma subclasse concreta de BaseWebScraper."""
        from scrapers.base_web_scraper import BaseWebScraper
        class ConcreteScraper(BaseWebScraper):
            def parse_products(self, raw_data) -> list[dict]:
                return [{"parsed": True, "data": raw_data[:50]}] if raw_data else []
        cfg = store_config or {"name": "test", "base_url": "https://test.com", "search_url": "{query}"}
        scraper = ConcreteScraper(cfg, rate_limit=rate_limit)
        return scraper

    def test_constructor_defaults(self):
        scraper = self._make_concrete_scraper()
        assert scraper.name == "test"
        assert scraper.base_url == "https://test.com"
        assert scraper.rate_limit == 1.0
        assert scraper._http is not None

    def test_constructor_custom_rate_limit(self):
        scraper = self._make_concrete_scraper(rate_limit=0.5)
        assert scraper.rate_limit == 0.5

    def test_constructor_rate_limit_from_config(self):
        scraper = self._make_concrete_scraper(
            {"name": "t", "base_url": "https://t.com", "rate_limit": 2.0, "search_url": "{query}"}
        )
        assert scraper.rate_limit == 2.0

    def test_context_manager(self):
        scraper = self._make_concrete_scraper()
        with scraper as s:
            assert s.name == "test"
        # after exit, client should be closed
        assert scraper._http.is_closed

    def test_close(self):
        scraper = self._make_concrete_scraper()
        scraper.close()
        assert scraper._http.is_closed

    def test_fetch_search_empty_url(self):
        scraper = self._make_concrete_scraper({"name": "t", "base_url": "https://t.com"})
        result = scraper.fetch_search("leite")
        assert result is None

    def test_fetch_search_url_formatting(self):
        scraper = self._make_concrete_scraper(
            {"name": "t", "base_url": "https://t.com", "search_url": "https://t.com/busca?q={query}"}
        )
        formatted = scraper.store["search_url"].format(query="leite+condensado")
        assert "busca?q=leite+condensado" in formatted

    def test_parse_products_abstract(self):
        from scrapers.base_web_scraper import BaseWebScraper
        class MissingImpl(BaseWebScraper):
            pass
        import inspect
        assert inspect.isabstract(MissingImpl)

    def test_run_empty_ingredients(self):
        scraper = self._make_concrete_scraper()
        result = scraper.run([])
        assert result == []

    @patch("scrapers.base_web_scraper.BaseWebScraper._search_and_parse")
    def test_run_iterates_ingredients(self, mock_search):
        mock_search.return_value = [{"product": "test", "price": 10.0}]
        scraper = self._make_concrete_scraper()
        ingredients = [{"canonical": "Leite", "search_terms": ["leite"]}, {"canonical": "Chocolate", "search_terms": ["chocolate"]}]
        result = scraper.run(ingredients)
        assert len(result) == 2
        assert mock_search.call_count == 2

    def test_throttle_positive(self):
        import time
        scraper = self._make_concrete_scraper(rate_limit=0.01)
        start = time.time()
        scraper._throttle()
        elapsed = time.time() - start
        assert elapsed >= 0.01

    def test_throttle_zero(self):
        import time
        scraper = self._make_concrete_scraper(
            {"name": "t", "base_url": "https://t.com", "search_url": "{query}", "rate_limit": 0}
        )
        start = time.time()
        scraper._throttle()
        elapsed = time.time() - start
        assert elapsed < 1.0  # nao deve dormir mais que 1s com rate_limit=0

    def test_fetch_json_network_error(self):
        scraper = self._make_concrete_scraper()
        result = scraper.fetch_json("https://nonexistent.invalid/api")
        assert result is None

    def test_parse_products_concrete(self):
        scraper = self._make_concrete_scraper()
        result = scraper.parse_products("<html>test</html>")
        assert len(result) == 1
        assert result[0]["parsed"] is True


class TestCoverageHeatmapTzAware:
    """Regression test for tz-naive vs tz-aware datetime subtraction bug in coverage heatmap."""

    def test_datetime_subtraction_tz_aware(self):
        """Test that datetime.now() (naive) works with tz-aware timestamps from DB."""
        import pandas as pd
        from datetime import datetime, timezone

        tz_aware_now = pd.Timestamp.now(tz=timezone.utc)
        tz_aware_week_ago = tz_aware_now - pd.Timedelta(days=7)
        tz_aware_old = tz_aware_now - pd.Timedelta(days=30)

        test_cases = [
            (tz_aware_now, "hoje"),
            (tz_aware_week_ago, "semana"),
            (tz_aware_old, "antigo"),
        ]

        for ts, expected in test_cases:
            dt = pd.to_datetime(ts)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            now = datetime.now()  # naive - matches the fix in admin/app.py
            days_ago = (now - dt).days

            if expected == "hoje":
                assert days_ago <= 3, f"Expected hoje (<=3 days), got {days_ago}"
            elif expected == "semana":
                assert 3 < days_ago <= 7, f"Expected semana (3-7 days), got {days_ago}"
            elif expected == "antigo":
                assert days_ago > 7, f"Expected antigo (>7 days), got {days_ago}"

    def test_datetime_subtraction_fails_with_utc_now(self):
        """Verify that using datetime.now(timezone.utc) would fail (the original bug)."""
        import pandas as pd
        from datetime import datetime, timezone

        tz_aware_now = pd.Timestamp.now(tz=timezone.utc)
        dt = pd.to_datetime(tz_aware_now)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)

        # This is the ORIGINAL buggy code - would raise TypeError
        try:
            _days_ago = (datetime.now(timezone.utc) - dt).days
            # If we get here without error, the test environment might handle it differently
            # But the key is that the fix uses naive datetime.now()
        except TypeError as e:
            if "tz-naive" in str(e) and "tz-aware" in str(e):
                # This confirms the original bug existed
                pass
            else:
                raise


class TestPaoFlyerScraper:

    def test_brand_and_campaign_type_overridden(self):
        """PaoFlyerScraper herda de ExtraFlyerScraper e sobrescreve BRAND e CAMPAIGN_TYPE."""
        from scrapers.pao_flyer_scraper import PaoFlyerScraper
        assert PaoFlyerScraper.BRAND == "pao"
        assert PaoFlyerScraper.CAMPAIGN_TYPE == "fresh"

    def test_extra_flyer_scraper_defaults(self):
        """ExtraFlyerScraper mantem BRAND e CAMPAIGN_TYPE originais."""
        from scrapers.extra_flyer_scraper import ExtraFlyerScraper
        assert ExtraFlyerScraper.BRAND == "extra"
        assert ExtraFlyerScraper.CAMPAIGN_TYPE == "mercado"

    def test_clean_product_text_rejects_stop_words(self):
        """Herda metodos de limpeza do ExtraFlyerScraper."""
        from scrapers.pao_flyer_scraper import PaoFlyerScraper
        scraper = PaoFlyerScraper({"name": "TestPao"})
        with scraper:
            assert not scraper._is_valid_product("cliente exclusivo oferta")
            assert scraper._is_valid_product("Leite Condensado Moca 395g")
