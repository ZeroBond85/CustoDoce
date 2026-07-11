"""Consumer tests: MOCK_REVIEW_QUEUE drives review_queue_service logic (DB mockado)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services import review_queue_service
from tests.unit.fixtures.mock_data import MOCK_REVIEW_QUEUE, MOCK_STORES


def test_mock_review_queue_normalize_text_strips_accents():
    raw = MOCK_REVIEW_QUEUE[0]["raw_product"]
    norm = review_queue_service._normalize_text(raw)
    assert norm == "leite cond piracanjuba 395g"
    assert "ç" not in norm and "ã" not in norm


def test_mock_review_queue_fuzzy_find_store_exact():
    with patch.object(review_queue_service, "get_all_stores", return_value=MOCK_STORES):
        found = review_queue_service._fuzzy_find_store("Assaí Atacadista")
    assert found is not None
    assert found["name"] == "Assaí Atacadista"


def test_mock_review_queue_fuzzy_find_store_substring():
    with patch.object(review_queue_service, "get_all_stores", return_value=MOCK_STORES):
        found = review_queue_service._fuzzy_find_store("assai")
    assert found is not None
    assert found["name"] == "Assaí Atacadista"


def test_mock_review_queue_insert_returns_record():
    item = MOCK_REVIEW_QUEUE[0]
    mock_client = MagicMock()
    # sem item existente -> insert
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[])
    )
    mock_client.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
        data=[{"id": "review-001"}]
    )
    with patch.object(review_queue_service, "get_service_client", return_value=mock_client):
        result = review_queue_service.insert_review_item(item)
    assert result.get("id") == "review-001"
