from datetime import date, timedelta
from unittest.mock import patch

from tests.unit.test_services.conftest import SAMPLE_HISTORY, SAMPLE_PRICES, make_mocks


class TestPriceService:
    # ── upsert_price ───────────────────────────────────────────

    @patch("services.price_repository.get_service_client")
    def test_upsert_price_payload_complete(self, mock_get_client):
        """Monta payload com todos os campos novos."""
        from services.price_service import upsert_price

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        entry = {
            "ingredient_id": "Leite Condensado Integral",
            "store_id": "test_store",
            "store_name": "Test Store",
            "raw_product": "Leite Moca",
            "raw_price": 42.90,
            "raw_unit": "cx 12x395g",
            "validity_raw": "Promocao valida ate 30/06",
            "tier": 1,
            "confidence": 0.95,
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

    @patch("services.price_repository.get_service_client")
    def test_upsert_price_detects_promotion(self, mock_get_client):
        """Detecta promocao pelo nome do produto."""
        from services.price_service import upsert_price

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        upsert_price(
            {
                "ingredient_id": "Teste",
                "store_id": "t",
                "store_name": "T",
                "raw_product": "Moca PROMO 50% OFF",
                "raw_price": 10.0,
                "raw_unit": "un",
            }
        )

        _, rpc_params = mock_client._captured_rpc
        assert rpc_params["p_is_promotion"] is True

    @patch("services.price_repository.get_service_client")
    def test_upsert_price_no_promotion(self, mock_get_client):
        """Nao marca promocao sem keywords."""
        from services.price_service import upsert_price

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        upsert_price(
            {
                "ingredient_id": "Teste",
                "store_id": "t",
                "store_name": "T",
                "raw_product": "Farinha de Trigo",
                "raw_price": 5.0,
                "raw_unit": "1kg",
            }
        )

        _, rpc_params = mock_client._captured_rpc
        assert rpc_params["p_is_promotion"] is False

    @patch("services.price_repository.get_service_client")
    def test_upsert_price_default_valid_until(self, mock_get_client):
        """Calcula valid_until default +7 dias."""
        from services.price_service import upsert_price

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        upsert_price(
            {
                "ingredient_id": "Teste",
                "store_id": "t",
                "store_name": "T",
                "raw_product": "Teste",
                "raw_price": 10.0,
                "raw_unit": "un",
            }
        )

        expected = (date.today() + timedelta(days=7)).isoformat()
        _, rpc_params = mock_client._captured_rpc
        assert rpc_params["p_valid_until"] == expected, f"Esperado {expected}, obtido {rpc_params['p_valid_until']}"

    # ── search_prices ──────────────────────────────────────────

    @patch("services.price_repository.get_supabase")
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

    @patch("services.price_repository.get_supabase")
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

    @patch("services.price_repository.get_supabase")
    def test_search_prices_empty_result(self, mock_get):
        """Retorna lista vazia quando sem dados."""
        from services.price_service import search_prices

        mock_client, _, _ = make_mocks()
        mock_get.return_value = mock_client

        result = search_prices("Inexistente")
        assert result == []

    @patch("services.price_repository.get_supabase")
    def test_search_prices_default_order_asc(self, mock_get):
        """Ordena por price_per_kg ASC no server (generated column)."""
        from services.price_service import search_prices

        mock_client, _, qb = make_mocks()
        qb._return_data = SAMPLE_PRICES
        mock_get.return_value = mock_client

        result = search_prices("Leite Condensado Integral")

        # server-side: order aplicado via generated column price_per_kg
        orders = [f for f in qb._applied_filters if f[0] == "order"]
        assert len(orders) == 1, f"Esperado 1 order, encontrado: {orders}"
        assert orders[0] == ("order", "price_per_kg", False), f"Order errado: {orders}"
        # resultado já vem ordenado do server
        assert len(result) > 0

    # ── get_latest_prices ──────────────────────────────────────

    @patch("services.price_repository.get_supabase")
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

    @patch("services.price_repository.get_supabase")
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

    @patch("services.price_repository.get_supabase")
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

    @patch("services.price_repository.get_supabase")
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

    @patch("services.review_queue_service.get_service_client")
    def test_insert_review_item_with_validity(self, mock_get_client):
        """Inclui validity_raw no payload."""
        from services.price_service import insert_review_item

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        insert_review_item(
            {
                "raw_product": "Leite Ninho 400g Oferta",
                "raw_price": 25.90,
                "raw_unit": "un",
                "store_name": "Extra",
                "source": "automated",
                "confidence": 0.65,
                "suggestions": ["Leite Ninho Integral"],
                "validity_raw": "Promocao semana do cliente",
            }
        )

        assert qb._captured_insert is not None
        assert qb._captured_insert["raw_product"] == "Leite Ninho 400g Oferta"
        assert qb._captured_insert["validity_raw"] == "Promocao semana do cliente"
        assert qb._captured_insert["status"] == "pending"

    @patch("services.review_queue_service.get_service_client")
    def test_insert_review_item_dedup_any_status(self, mock_get_client):
        """Dedup funciona independente do status (pending, approved, rejected)."""
        from services.price_service import insert_review_item

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        # Simula item existente com status "approved"
        qb._return_data = [{"id": "existing-id"}]

        result = insert_review_item(
            {
                "raw_product": "Ninho Integral 400g",
                "raw_price": 25.90,
                "raw_unit": "un",
                "store_name": "Extra",
                "source": "automated",
                "confidence": 0.65,
                "suggestions": ["Leite Ninho Integral"],
                "validity_raw": "",
            }
        )

        # Deve retornar o existente e NAO inserir novo
        assert result["id"] == "existing-id"
        assert qb._captured_insert is None, "Nao deveria inserir novo registro"

        # Verifica que checou store_name + raw_product SEM filtro de status
        eq_filters = [f for f in qb._applied_filters if f[0] == "eq"]
        eq_fields = [f[1] for f in eq_filters]
        assert "store_name" in eq_fields
        assert "raw_product" in eq_fields
        assert "status" not in eq_fields, "Nao deveria filtrar por status"

    # ── auto_reject_stale_review_items ───────────────────────────

    @patch("services.review_queue_service.get_service_client")
    def test_auto_reject_stale_rejects_low_confidence_pending(self, mock_get_client):
        from services.price_service import auto_reject_stale_review_items

        mock_client, _, qb = make_mocks()
        qb._return_data = [
            {"id": "old1", "confidence": 0.3},
            {"id": "old2", "confidence": 0.5},
            {"id": "old3", "confidence": 0.8},  # above threshold
        ]
        mock_get_client.return_value = mock_client
        count = auto_reject_stale_review_items(max_age_days=7, min_confidence=0.6)
        assert count == 2  # old1 and old2 rejected

    @patch("services.review_queue_service.get_service_client")
    def test_auto_reject_stale_handles_string_confidence(self, mock_get_client):
        from services.price_service import auto_reject_stale_review_items

        mock_client, _, qb = make_mocks()
        qb._return_data = [
            {"id": "old1", "confidence": "0.4"},
            {"id": "old2", "confidence": 0.9},
        ]
        mock_get_client.return_value = mock_client
        count = auto_reject_stale_review_items(max_age_days=7, min_confidence=0.6)
        assert count == 1

    @patch("services.review_queue_service.get_service_client")
    def test_auto_reject_stale_empty_queue(self, mock_get_client):
        from services.price_service import auto_reject_stale_review_items

        mock_client, _, qb = make_mocks()
        qb._return_data = []
        mock_get_client.return_value = mock_client
        count = auto_reject_stale_review_items()
        assert count == 0

    # ── reject_review_item ─────────────────────────────────────

    @patch("services.review_queue_service.get_service_client")
    def test_reject_review_item_sets_rejected(self, mock_get_client):
        """Rejeita: marca status rejected."""
        from services.price_service import reject_review_item

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        reject_review_item("r1")

        assert qb._captured_update is not None, "update() deveria ser chamado"

    # ── get_telegram_report ────────────────────────────────────

    @patch("services.price_repository.get_supabase")
    def test_get_telegram_report_empty(self, mock_get):
        """Lista vazia de ingredientes retorna lista vazia."""
        from services.price_service import get_telegram_report

        mock_client, _, _ = make_mocks()
        mock_get.return_value = mock_client

        assert get_telegram_report([], top_n=5) == []

    @patch("services.price_repository.get_supabase")
    def test_get_telegram_report_ignores_connection_error(self, mock_get):
        """Nao quebra se Supabase offline."""
        from services.price_service import get_telegram_report

        mock_get.side_effect = Exception("offline")

        result = get_telegram_report([{"canonical_name": "X", "aliases": []}], top_n=5)
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
            assert _detect_promotion(product, unit) == expected, f"Falhou: {product=} {unit=} -> esperado {expected}"

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

    @patch("services.price_repository.get_supabase")
    def test_get_prices_for_ingredient_default_order(self, mock_get):
        """Ordena por price_per_kg ASC no server (generated column)."""
        from services.price_service import get_prices_for_ingredient

        mock_client, _, qb = make_mocks()
        qb._return_data = SAMPLE_PRICES
        mock_get.return_value = mock_client

        result = get_prices_for_ingredient("Leite Condensado Integral")

        # server-side: order aplicado via generated column price_per_kg
        orders = [f for f in qb._applied_filters if f[0] == "order"]
        assert len(orders) == 1, f"Esperado 1 order, encontrado: {orders}"
        assert orders[0] == ("order", "price_per_kg", False), f"Order errado: {orders}"
        assert len(result) > 0

    # ── get_cheapest_prices ─────────────────────────────────────

    @patch("services.price_repository.search_prices")
    def test_get_cheapest_prices_basic(self, mock_search):
        """get_cheapest_prices() must call search_prices with correct params."""
        from services.price_service import get_cheapest_prices

        mock_search.return_value = [{"store_name": "Assai", "normalized": {"price_per_kg": 8.5}}]
        result = get_cheapest_prices("Leite Condensado", top_n=3)
        mock_search.assert_called_once_with(
            "Leite Condensado", sort_by="price_per_kg", sort_order="asc", limit=3, valid_only=True
        )
        assert len(result) == 1
        assert result[0]["store_name"] == "Assai"

    @patch("services.price_repository.search_prices")
    def test_get_cheapest_prices_empty(self, mock_search):
        """get_cheapest_prices() must return [] when no prices found."""
        from services.price_service import get_cheapest_prices

        mock_search.return_value = []
        result = get_cheapest_prices("Inexistente")
        assert result == []

    # ── main.process_price_match ───────────────────────────────────

    @patch("services.collector.upsert_price")
    @patch("services.collector.match_ingredient")
    def test_process_price_match_sets_validity_fields(self, mock_match, mock_upsert):
        """process_price_match() deve incluir validity_raw, is_promotion, collected_weekday."""
        from services.collector import process_price_match

        mock_match.return_value = (
            {"canonical_name": "Leite Condensado", "aliases": [], "search_terms": ["leite"]},
            95.0,
            "exato",
        )

        store = {"name": "Assai", "type": "pdf", "tier": 1, "city": "Santos"}
        ing_list = [
            {"canonical_name": "Leite Condensado", "aliases": ["leite moca"], "search_terms": ["leite condensado"]}
        ]
        result = process_price_match(store, "Leite Moca PROMO 50% OFF", 39.90, "cx 12x395g", ing_list)

        assert result is not None
        assert result["is_promotion"] is True
        assert result["validity_raw"] == ""
        assert result["collected_weekday"] in ("Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom")

    @patch("services.collector.upsert_price")
    @patch("services.collector.match_ingredient")
    def test_process_price_match_no_promotion(self, mock_match, mock_upsert):
        """Sem keywords de promocao, is_promotion=False."""
        from services.collector import process_price_match

        mock_match.return_value = (
            {"canonical_name": "Farinha", "aliases": [], "search_terms": ["farinha"]},
            95.0,
            "exato",
        )

        store = {"name": "Assai", "type": "pdf", "tier": 1}
        ing_list = [{"canonical_name": "Farinha", "aliases": ["farinha trigo"], "search_terms": ["farinha de trigo"]}]
        result = process_price_match(store, "Farinha de Trigo 1kg", 5.90, "1kg", ing_list)

        assert result is not None
        assert result["is_promotion"] is False

    @patch("services.collector.insert_review_item")
    @patch("services.collector.match_ingredient")
    def test_process_price_match_review_has_validity(self, mock_match, mock_insert):
        """Review queue deve receber validity_raw."""
        from services.collector import process_price_match

        with patch("parsers.llm_classifier.LLMClassifier") as mock_llm:
            mock_llm.return_value.classify_sync.return_value = None
            mock_match.return_value = (None, 70.0, "fuzzy")

            store = {"name": "Extra", "type": "website"}
            ing_list = [{"canonical_name": "Leite Condensado", "aliases": [], "search_terms": ["leite condensado"]}]
            process_price_match(store, "Leite Produto Desconto 30%", 15.0, "un", ing_list, validity_raw="Promo Semanal")

            inserted = mock_insert.call_args[0][0]
            assert inserted["validity_raw"] == "Promo Semanal"
            assert inserted["confidence"] == 0.7

    @patch("services.collector.upsert_price")
    @patch("services.collector.match_ingredient")
    def test_process_price_match_passes_validity_raw(self, mock_match, mock_upsert):
        """Validity_raw fornecido externamente deve ser passado ao entry."""
        from services.collector import process_price_match

        mock_match.return_value = (
            {"canonical_name": "Leite Ninho", "aliases": [], "search_terms": ["leite"]},
            90.0,
            "exato",
        )

        store = {"name": "Extra", "type": "website", "tier": 2}
        ing_list = [{"canonical_name": "Leite Ninho", "aliases": ["ninho"], "search_terms": ["leite em po"]}]
        result = process_price_match(
            store,
            "Leite Ninho Integral 400g",
            25.90,
            "un",
            ing_list,
            validity_raw="Oferta valida ate 30/06",
        )

        assert result is not None
        assert result["validity_raw"] == "Oferta valida ate 30/06"

    @patch("services.collector.upsert_price")
    @patch("services.collector.match_ingredient")
    def test_process_price_match_extracts_date_from_product(self, mock_match, mock_upsert):
        """Extrai texto de validade do nome do produto quando validity_raw nao fornecido."""
        from services.collector import process_price_match

        mock_match.return_value = ({"canonical_name": "Teste", "aliases": [], "search_terms": ["teste"]}, 95.0, "exato")

        store = {"name": "Test", "type": "pdf", "tier": 1}
        ing_list = [{"canonical_name": "Teste", "aliases": ["produto"], "search_terms": ["teste", "produto"]}]
        result = process_price_match(
            store,
            "Produto Teste ate 30/06/2026",
            10.0,
            "un",
            ing_list,
        )

        assert result is not None
        assert "30/06" in result["validity_raw"]


class TestUpsertPriceResilience:
    """Regression: [Errno 11] Resource temporarily unavailable must NOT lose a
    collected price — upsert_price retries transient network errors."""

    @patch("services.price_repository.get_service_client")
    def test_rpc_transient_errno11_is_retried(self, mock_get_client):
        """RPC levanta [Errno 11] duas vezes e depois sucede: deve retornar ok."""
        from services.price_repository import upsert_price
        from tests.unit.test_services.conftest import MockQueryBuilder, MockQueryResult, MockSupabaseClient

        rpc_calls = {"n": 0}

        class _RpcQb(MockQueryBuilder):
            def execute(self):
                rpc_calls["n"] += 1
                if rpc_calls["n"] <= 2:
                    raise RuntimeError("[Errno 11] Resource temporarily unavailable")
                return MockQueryResult([{"ok": True}])

        qb = _RpcQb([])
        mock_client = MockSupabaseClient(qb)
        mock_get_client.return_value = mock_client

        entry = {
            "ingredient_id": "Leite Condensado Integral",
            "store_id": "test_store",
            "store_name": "Test Store",
            "raw_product": "Leite Moca",
            "raw_price": 42.90,
            "raw_unit": "cx 12x395g",
        }
        result = upsert_price(entry)
        assert rpc_calls["n"] == 3, "deve retryar ate o sucesso"
        assert result is not None

    @patch("services.price_repository.get_service_client")
    def test_rpc_transient_then_fallback_succeeds(self, mock_get_client):
        """RPC sempre [Errno 11] -> cai no table.upsert que também falha 2x e sucede."""
        from services.price_repository import upsert_price
        from tests.unit.test_services.conftest import MockQueryBuilder, MockQueryResult, MockSupabaseClient, MockTable

        rpc_calls = {"n": 0}
        tbl_calls = {"n": 0}

        class _RpcQb(MockQueryBuilder):
            def execute(self):
                rpc_calls["n"] += 1
                raise RuntimeError("[Errno 11] Resource temporarily unavailable")

        class _TblQb(MockQueryBuilder):
            def execute(self):
                tbl_calls["n"] += 1
                if tbl_calls["n"] <= 2:
                    raise RuntimeError("[Errno 11] Resource temporarily unavailable")
                return MockQueryResult([{"ok": True}])

        rpc_qb = _RpcQb([])
        tbl_qb = _TblQb([])
        mock_client = MockSupabaseClient(rpc_qb)
        mock_client.table = lambda name: MockTable(tbl_qb)
        mock_get_client.return_value = mock_client

        entry = {
            "ingredient_id": "Leite Condensado Integral",
            "store_id": "test_store",
            "store_name": "Test Store",
            "raw_product": "Leite Moca",
            "raw_price": 42.90,
            "raw_unit": "cx 12x395g",
        }
        result = upsert_price(entry)
        # RPC tentou 3x, fallback table tentou 3x (2 falhas + 1 sucesso)
        assert rpc_calls["n"] == 3
        assert tbl_calls["n"] == 3
        assert result is not None
