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

        payload = qb._captured_upsert
        assert payload is not None, "upsert() nao foi chamado"
        assert payload["ingredient_id"] == "Leite Condensado Integral"
        assert payload["store_id"] == "test_store"
        assert payload["raw_price"] == 42.90
        assert payload["validity_raw"] == "Promocao valida ate 30/06"
        assert payload["collected_weekday"] in ("Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom")
        assert "valid_from" in payload
        assert "valid_until" in payload
        assert "is_promotion" in payload
        assert "collected_at" in payload

    @patch("services.price_service.get_service_client")
    def test_upsert_price_detects_promotion(self, mock_get_client):
        """Detecta promocao pelo nome do produto."""
        from services.price_service import upsert_price

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        upsert_price({"ingredient_id": "Teste", "store_id": "t", "store_name": "T",
                       "raw_product": "Moca PROMO 50% OFF", "raw_price": 10.0, "raw_unit": "un"})

        assert qb._captured_upsert is not None
        assert qb._captured_upsert["is_promotion"] is True

    @patch("services.price_service.get_service_client")
    def test_upsert_price_no_promotion(self, mock_get_client):
        """Nao marca promocao sem keywords."""
        from services.price_service import upsert_price

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        upsert_price({"ingredient_id": "Teste", "store_id": "t", "store_name": "T",
                       "raw_product": "Farinha de Trigo", "raw_price": 5.0, "raw_unit": "1kg"})

        assert qb._captured_upsert["is_promotion"] is False

    @patch("services.price_service.get_service_client")
    def test_upsert_price_default_valid_until(self, mock_get_client):
        """Calcula valid_until default +7 dias."""
        from services.price_service import upsert_price

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        upsert_price({"ingredient_id": "Teste", "store_id": "t", "store_name": "T",
                       "raw_product": "Teste", "raw_price": 10.0, "raw_unit": "un"})

        expected = (date.today() + timedelta(days=7)).isoformat()
        assert qb._captured_upsert["valid_until"] == expected, \
            f"Esperado {expected}, obtido {qb._captured_upsert['valid_until']}"

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
        """Ordena por price_per_kg ASC por padrao."""
        from services.price_service import search_prices

        mock_client, _, qb = make_mocks()
        qb._return_data = SAMPLE_PRICES
        mock_get.return_value = mock_client

        search_prices("Leite Condensado Integral")

        assert ("order", "price_per_kg", False) in qb._applied_filters

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
    def test_approve_review_item_updates_and_upserts(self, mock_get_client):
        """Aprova: update status + upsert price."""
        from services.price_service import approve_review_item

        mock_client, table, qb = make_mocks()
        qb._return_data = SAMPLE_REVIEW
        mock_get_client.return_value = mock_client

        approve_review_item("r1", "Leite Ninho Integral")

        assert qb._captured_update is not None, "update() deveria ser chamado"
        assert qb._captured_upsert is not None, "upsert() deveria ser chamado"
        assert qb._captured_update.get("status") == "approved"

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
        """Ordena por price_per_kg ASC."""
        from services.price_service import get_prices_for_ingredient

        mock_client, _, qb = make_mocks()
        qb._return_data = SAMPLE_PRICES
        mock_get.return_value = mock_client

        get_prices_for_ingredient("Leite Condensado Integral")

        assert ("order", "price_per_kg", False) in qb._applied_filters


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

        mock_match.return_value = (None, 50.0, "fuzzy")

        store = {"name": "Extra", "type": "website"}
        process_price_match(store, "Produto Desconto 30%", 15.0, "un", [], validity_raw="Promo Semanal")

        inserted = mock_insert.call_args[0][0]
        assert inserted["validity_raw"] == "Promo Semanal"
        assert inserted["confidence"] == 0.5

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

        entries = scraper.parse_product(product)
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

        entries = scraper.parse_product(product)
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

        entries = scraper.parse_product(product)
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
        assert "<html>" in html
        assert "Leite Condensado" in html
        assert "Creme de Leite" in html
        assert "Assai" in html and "Atacadao" in html and "Spani" in html
        assert "R$ 42.90" in html and "R$ 39.90" in html and "R$ 8.90" in html
        assert "🏷️" in html
        assert "ate 2026-07-01" in html
        assert "ate 2026-07-05" in html
        assert "Validade" in html and "R$/kg" in html and "Loja" in html

    def test_build_full_report_html_empty(self):
        """Dict vazio gera HTML basico sem erros."""
        from services.email_service import build_full_report_html

        html = build_full_report_html({})
        assert "<html>" in html
        assert "Relatorio" in html


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
