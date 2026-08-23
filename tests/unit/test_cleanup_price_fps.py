"""Unit tests para scripts/cleanup_price_fps.py — rewrite client nativo PostgREST.

Audit item #2 (PR-03): o script usava f-string SQL interpolando IDs vindos do
DB (classe S608/B608). Agora é 100% query builder (.or_/.in_/count="exact").
Estes testes travam o formato da query gerada E o chunking de deletes,
além de regressão source-level (sem RPC exec_sql, sem f-string SQL).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts import cleanup_price_fps as cpf  # noqa: E402

SCRIPT_PATH = Path("scripts/cleanup_price_fps.py")


class FakeResponse:
    def __init__(self, rows):
        self.data = list(rows)
        self.count = len(rows)


class FakeQuery:
    """Chainable capturando cada chamada do query builder."""

    def __init__(self, sink, rows=None):
        self._sink = sink
        self._rows = rows or []
        self._in_values: tuple = ()
        self._is_delete = False

    def select(self, columns, **kwargs):
        self._sink.append(("select", columns, kwargs))
        return self

    def or_(self, clause):
        self._sink.append(("or_", clause))
        return self

    def order(self, column, desc=False):
        self._sink.append(("order", column, desc))
        return self

    def limit(self, n):
        self._sink.append(("limit", n))
        return self

    def in_(self, column, values):
        self._sink.append(("in", column, tuple(values)))
        self._in_values = tuple(values)
        return self

    def delete(self):
        self._sink.append(("delete",))
        self._is_delete = True
        return self

    def execute(self):
        self._sink.append(("execute",))
        if self._is_delete:
            # PostgREST devolve as linhas deletadas (returning default)
            return FakeResponse([{"id": v} for v in self._in_values])
        return FakeResponse(self._rows)


class FakeClient:
    def __init__(self, rows=None):
        self.calls: list = []
        self._rows = rows or []

    def table(self, name):
        self.calls.append(("table", name))
        return FakeQuery(self.calls, self._rows)


# ── Query shape ──────────────────────────────────────────────────────


def test_list_fps_builds_native_or_ilike_query():
    fc = FakeClient()
    rows = cpf._list_fps(fc, limit=7)
    assert rows == []
    assert fc.calls[0] == ("table", "prices")
    sel = next(c for c in fc.calls if c[0] == "select")
    assert sel[1] == "id,store_id,ingredient_id,raw_price,raw_product"
    or_call = next(c for c in fc.calls if c[0] == "or_")
    clause = or_call[1]
    assert clause.startswith("raw_product.ilike.*papel*")
    assert "," in clause and clause.count("ilike.") == len(cpf._NON_FOOD_PATTERNS)
    assert "%" not in clause, "wildcard deve ser '*' (convenção PostgREST), não '%'"
    order = next(c for c in fc.calls if c[0] == "order")
    assert order[1] == "created_at" and order[2] is True
    lim = next(c for c in fc.calls if c[0] == "limit")
    assert lim[1] == 7


def test_count_by_ingredients_uses_count_exact():
    fc = FakeClient(rows=[{"id": "a"}, {"id": "b"}, {"id": "c"}])
    n = cpf._count_by_ingredients(fc, ["ing1"])
    sel = next(c for c in fc.calls if c[0] == "select")
    assert sel[2] == {"count": "exact"}
    ins = [c for c in fc.calls if c[0] == "in"]
    assert ins and ins[0][1] == "ingredient_id" and ins[0][2] == ("ing1",)
    assert n == 3


def test_count_by_ingredients_empty_short_circuits():
    fc = FakeClient()
    assert cpf._count_by_ingredients(fc, []) == 0
    assert fc.calls == [], "não deve construir query para lista vazia"


def test_count_total_prices_single_row_payload():
    fc = FakeClient(rows=[{"id": str(i)} for i in range(42)])
    assert cpf._count_total_prices(fc) == 42
    lim = next(c for c in fc.calls if c[0] == "limit")
    assert lim[1] == 1, "payload mínimo — contagem vem do header count"


# ── Chunking de deletes (query-string ~8KB) ─────────────────────────


def test_delete_chunks_of_max_100():
    fc = FakeClient()
    ids = [f"{i:03d}-aaaa-bbbb-cccc-dddddddddddd" for i in range(250)]
    deleted = cpf._delete_in_chunks(fc, "id", ids)
    ins_calls = [(c[1], c[2]) for c in fc.calls if c[0] == "in"]
    sizes = [len(vals) for _, vals in ins_calls]
    assert sizes == [100, 100, 50]
    assert all(col == "id" for col, _ in ins_calls)
    assert deleted == 250  # fake devolve os chunks como deletados


def test_delete_fps_deletes_confirmed_fps():
    fc = FakeClient(rows=[{"id": "fp1", "raw_product": "Forminha Papel"}])
    # raw_product casa padrão legit? "forminha papel" não está em _LEGIT → é FP
    n = cpf._delete_fps(fc)
    assert n == 1
    dels = [c for c in fc.calls if c[0] == "delete"]
    assert dels, "delete nativo deve ser usado"


# ── Regressão source-level (audit item #2) ──────────────────────────


def test_script_has_no_dynamic_sql():
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "exec_sql" not in src, "deletes devem ser client nativo, não RPC exec_sql"
    assert ".rpc(" not in src
    assert "noqa: S608" not in src
    for marker in ('f"SELECT', "f'SELECT", 'f"DELETE', "f'DELETE"):
        assert marker not in src, "f-string SQL proibida"


def test_validate_shape():
    class FC(FakeClient):
        pass

    fc = FC(rows=[{"id": "x"}])
    out = cpf._validate(fc)
    assert set(out) >= {
        "fps_remaining",
        "test_data_remaining",
        "orphan_remaining",
        "total_prices",
        "validated_at",
    }
