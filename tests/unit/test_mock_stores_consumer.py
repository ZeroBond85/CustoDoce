"""Consumer tests: MOCK_STORES drive store_registry normalization + dedup logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services import store_registry
from tests.unit.fixtures.mock_data import MOCK_STORES


def test_mock_stores_normalize_name_idempotent():
    for store in MOCK_STORES:
        norm = store_registry.normalize_name(store["name"])
        assert norm == norm.upper()
        assert all(c.isalnum() or c == " " for c in norm)
        assert store_registry.normalize_name(norm) == norm


def test_mock_stores_normalize_strips_accents_and_symbols():
    # normalize_name remove acentos e símbolos (í -> dropado)
    assert store_registry.normalize_name("Assaí Atacadista") == "ASSA ATACADISTA"
    assert store_registry.normalize_name("Mercado Livre!!") == "MERCADO LIVRE"


def test_mock_stores_find_similar_returns_exact_match():
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=MOCK_STORES)
    )
    with patch.object(store_registry, "get_service_client", return_value=mock_client):
        results = store_registry.find_similar_stores("ASSAI ATACADISTA", threshold=90)
    assert results, "esperado ao menos 1 similar"
    assert results[0]["name"] == "Assaí Atacadista"
    assert results[0]["similarity"] >= 0.9


def test_mock_stores_find_similar_below_threshold_empty():
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=MOCK_STORES)
    )
    with patch.object(store_registry, "get_service_client", return_value=mock_client):
        results = store_registry.find_similar_stores("TOTALMENTE DIFERENTE XYZ", threshold=99)
    assert results == []
