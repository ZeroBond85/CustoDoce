"""Unit tests for services/store_registry.py (discover + entry + dataclass)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services import store_registry


def test_store_registry_entry_dataclass_defaults():
    entry = store_registry.StoreRegistryEntry(name="Loja X")
    assert entry.name == "Loja X"
    assert entry.normalized_name == "LOJA X"
    assert entry.status == "pending_review"
    assert entry.config == {}


def test_discover_stores_from_flyers_calls_rpc():
    mock_client = MagicMock()
    mock_client.rpc.return_value.execute.return_value = SimpleNamespace(data=[])
    with patch.object(store_registry, "get_service_client", return_value=mock_client):
        result = store_registry.discover_stores_from_flyers()
    assert result == 0
    mock_client.rpc.assert_called_once_with("discover_stores_from_flyers")


def test_discover_stores_from_flyers_no_client_returns_zero():
    with patch.object(store_registry, "get_service_client", side_effect=Exception("no client")):
        result = store_registry.discover_stores_from_flyers()
    assert result == 0


def test_get_registry_entry_builds_dataclass():
    row = {
        "id": "reg-1",
        "name": "Nova Loja",
        "normalized_name": "NOVA LOJA",
        "tier": 3,
        "type": "manual",
        "logistics": "pickup_local",
        "city": "Santos",
        "zone": "Baixada",
        "coverage": "regional",
        "collection_method": "auto",
        "source": "auto",
        "status": "pending_review",
        "match_score": 0.5,
        "matched_store_id": None,
        "config": {},
    }
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
        SimpleNamespace(data=row)
    )
    with patch.object(store_registry, "get_service_client", return_value=mock_client):
        entry = store_registry.get_registry_entry("reg-1")
    assert entry is not None
    assert entry.name == "Nova Loja"
    assert entry.tier == 3
