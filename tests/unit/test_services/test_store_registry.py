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


def test_discover_stores_from_flyers_filters_non_food():
    """Non-food stores like Magazine Luiza should be filtered out before registry."""
    mock_client = MagicMock()
    # flyers query returns 3 stores: 2 food, 1 non-food
    mock_client.table.return_value.select.return_value.execute.return_value = SimpleNamespace(
        data=[
            {"store_name": "Assaí Atacadista", "region": "Santos", "city": "Santos"},
            {"store_name": "Magazine Luiza", "region": "Santos", "city": "Santos"},
            {"store_name": "Carrefour", "region": "São Paulo", "city": "São Paulo"},
        ]
    )
    with patch.object(store_registry, "get_service_client", return_value=mock_client), \
         patch.object(store_registry, "upsert_registry_entry",
                      return_value=SimpleNamespace(id="new-1", matched_store_id=None, address="")):
        result = store_registry.discover_stores_from_flyers()
    # 2 food stores (Assaí, Carrefour), Magazine Luiza filtered out
    assert result == 2
    calls = mock_client.table.call_args_list
    tables_called = [c[0][0] for c in calls]
    assert "flyers" in tables_called  # queried flyers
    assert "stores" in tables_called  # queried existing stores for dedup


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
