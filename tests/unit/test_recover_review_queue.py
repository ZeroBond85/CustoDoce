"""Testes de scripts/recover_review_queue.py — T1.3 archive-below + T1.4 reject-false-positives."""

import sys
from unittest.mock import patch

sys.path.insert(0, ".")


class _Query:
    def __init__(self, client, data):
        self.client = client
        self.data = data
        self.filters = []
        self._update_payload = None

    def update(self, payload):
        self._update_payload = payload
        return self

    def select(self, *a, **kw):
        return self

    def eq(self, field, value):
        self.filters.append(("eq", field, value))
        return self

    def lt(self, field, value):
        self.filters.append(("lt", field, value))
        return self

    def range(self, start, end):
        self.filters.append(("range", start, end))
        return self

    def execute(self):
        if self._update_payload is not None:
            self.client.updates.append({"payload": self._update_payload, "filters": list(self.filters)})
        return type("R", (), {"data": self.data})


class _Table:
    def __init__(self, client):
        self.client = client

    def select(self, *a, **kw):
        return _Query(self.client, self.client.pending_rows)

    def update(self, payload):
        q = _Query(self.client, self.client.pending_rows)
        q.update(payload)
        return q


class _FakeClient:
    def __init__(self, pending_rows):
        self.pending_rows = pending_rows
        self.updates = []
        self._last_table = None

    def table(self, name):
        self._last_table = name
        return _Table(self)


from scripts import recover_review_queue as rq  # noqa: E402


def test_archive_below_threshold_marks_rejected():
    """T1.3: update(status=rejected) com filtro lt(confidence, threshold)."""
    client = _FakeClient([{"id": "a", "confidence": 0.3}])
    with patch.object(rq, "client", client):
        count = rq.archive_below_threshold(threshold=0.70)
    assert count == 1
    assert len(client.updates) == 1
    upd = client.updates[0]
    assert upd["payload"] == {"status": "rejected"}
    lt_filters = [f for f in upd["filters"] if f[0] == "lt"]
    assert ("lt", "confidence", 0.70) in lt_filters


def test_archive_below_threshold_empty_queue():
    client = _FakeClient([])
    with patch.object(rq, "client", client):
        count = rq.archive_below_threshold(threshold=0.70)
    assert count == 0


def test_archive_below_threshold_custom_threshold():
    client = _FakeClient([{"id": "a", "confidence": 0.75}])
    with patch.object(rq, "client", client):
        rq.archive_below_threshold(threshold=0.80)
    lt_filters = [f for f in client.updates[0]["filters"] if f[0] == "lt"]
    assert ("lt", "confidence", 0.80) in lt_filters


def test_reject_false_positives_rejects_non_matching():
    """T1.4: pendentes que não casam com ingredientes ativos são rejeitados."""
    pending = [
        {"id": "fp1", "raw_product": "Biscoito Recheado Chocolate 140g", "confidence": 0.75},
        {"id": "ok1", "raw_product": "Leite Condensado Moca 395g", "confidence": 0.82},
    ]
    client = _FakeClient(pending)
    ingredients = [{"canonical_name": "Leite Condensado", "search_terms": ["leite condensado"]}]

    def fake_match(product, ing, threshold=80.0):
        if "leite condensado" in product.lower():
            return ing[0], 100.0, "exato"
        return None, 0.0, ""

    with patch.object(rq, "client", client), patch.object(rq, "match_ingredient", side_effect=fake_match):
        count = rq.reject_false_positives(ingredients=ingredients, threshold=60.0)
    assert count == 1
    assert len(client.updates) == 1
    assert client.updates[0]["payload"] == {"status": "rejected"}
    assert ("eq", "id", "fp1") in client.updates[0]["filters"]


def test_reject_false_positives_no_ingredients_nothing_rejected():
    """T1.4: sem candidatos não há rejeições (todos casam)."""
    pending = [
        {"id": "ok1", "raw_product": "Leite Condensado Moca 395g", "confidence": 0.82},
        {"id": "ok2", "raw_product": "Granulado Ao Leite 200g", "confidence": 0.85},
    ]
    client = _FakeClient(pending)
    ingredients = [{"canonical_name": "Leite Condensado", "search_terms": ["leite condensado"]}]

    def fake_match(product, ing, threshold=80.0):
        return ing[0], 100.0, "exato"

    with patch.object(rq, "client", client), patch.object(rq, "match_ingredient", side_effect=fake_match):
        count = rq.reject_false_positives(ingredients=ingredients, threshold=60.0)
    assert count == 0
    assert len(client.updates) == 0
