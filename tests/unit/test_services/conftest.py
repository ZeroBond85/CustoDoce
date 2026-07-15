"""Testes de servicos com mocks do Supabase — helpers compartilhados."""

import os
import sys

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

    def lt(self, field, value):
        self._applied_filters.append(("lt", field, value))
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

    def range(self, start, end):
        self._applied_filters.append(("range", start, end))
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
        if self._single_mode:
            self._single_mode = False
            return None
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
        "id": "1",
        "ingredient_id": "Leite Condensado Integral",
        "store_id": "assai",
        "store_name": "Assai",
        "raw_product": "Leite Condensado Moca 395g",
        "raw_price": 42.90,
        "raw_unit": "cx 12x395g",
        "collected_at": "2026-06-16T10:00:00",
        "valid_from": "2026-06-16",
        "valid_until": "2026-06-23",
        "validity_raw": "Validade: 23/06",
        "collected_weekday": "Ter",
        "is_promotion": False,
        "tier": 1,
        "confidence": 1.0,
        "normalized": {"qty": 12, "unit_kg": 0.395, "total_kg": 4.74, "price_per_kg": 9.05, "price_per_un": 3.58},
        "city": "Santos",
        "logistics": "pickup_local",
    },
    {
        "id": "2",
        "ingredient_id": "Leite Condensado Integral",
        "store_id": "atacadao",
        "store_name": "Atacadao",
        "raw_product": "Leite Moca PROMO",
        "raw_price": 39.90,
        "raw_unit": "cx 12x395g",
        "collected_at": "2026-06-16T10:30:00",
        "valid_from": "2026-06-16",
        "valid_until": "2026-06-30",
        "validity_raw": "Oferta valida ate 30/06",
        "collected_weekday": "Ter",
        "is_promotion": True,
        "tier": 1,
        "confidence": 1.0,
        "normalized": {"qty": 12, "unit_kg": 0.395, "total_kg": 4.74, "price_per_kg": 8.42, "price_per_un": 3.33},
        "city": "Santos",
        "logistics": "pickup_local",
    },
]

SAMPLE_REVIEW = [
    {
        "id": "r1",
        "raw_product": "Ninho Integral 400g",
        "raw_price": 25.90,
        "raw_unit": "un",
        "store_name": "Extra",
        "source": "automated",
        "confidence": 0.65,
        "suggestions": ["Leite Ninho Integral"],
        "validity_raw": "Promocao semana do cliente",
        "status": "pending",
        "collected_at": "2026-06-16T11:00:00",
    }
]

SAMPLE_HISTORY = [
    {
        "id": "h1",
        "price_id": "1",
        "ingredient_id": "Leite Condensado Integral",
        "store_id": "assai",
        "store_name": "Assai",
        "raw_product": "Leite Condensado Moca 395g",
        "raw_price": 45.00,
        "raw_unit": "cx 12x395g",
        "normalized": {"price_per_kg": 9.49, "price_per_un": 3.75},
        "valid_from": "2026-06-09",
        "valid_until": "2026-06-16",
        "validity_raw": "",
        "collected_weekday": "Ter",
        "is_promotion": False,
        "collected_at": "2026-06-09T10:00:00",
    },
]
