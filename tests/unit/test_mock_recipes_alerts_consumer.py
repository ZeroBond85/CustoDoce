"""Consumer tests: MOCK_RECIPES / MOCK_ALERT_RULES / MOCK_PRICE_HISTORY drive recipe + alert logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services import alert_service, recipe_service
from tests.unit.fixtures.mock_data import (
    MOCK_ALERT_RULES,
    MOCK_PRICE_HISTORY,
    MOCK_RECIPES,
    MOCK_RECIPE_ITEMS,
)


def test_mock_alert_rules_active_returned():
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=MOCK_ALERT_RULES)
    )
    with patch.object(alert_service, "get_supabase", return_value=mock_client):
        rules = alert_service.get_active_alert_rules()
    assert len(rules) == 1
    assert rules[0]["name"] == "Preço Alto Leite Condensado"


def test_mock_price_history_detects_drop():
    history = [
        {"normalized": {"price_per_kg": p["price_per_kg"]}} for p in MOCK_PRICE_HISTORY
    ]
    # preço atual bem abaixo da média histórica -> drop >=10%
    result = alert_service.check_price_drops("ing-001", 20.0, history)
    assert result is not None
    assert result["type"] == "price_drop"
    assert result["drop_pct"] > 10


def test_mock_price_history_no_drop_when_above_avg():
    history = [{"normalized": {"price_per_kg": p["price_per_kg"]}} for p in MOCK_PRICE_HISTORY]
    result = alert_service.check_price_drops("ing-001", 30.0, history)
    assert result is None


def test_mock_recipe_upsert_returns_id():
    recipe = MOCK_RECIPES[0]
    mock_client = MagicMock()
    mock_client.table.return_value.upsert.return_value.execute.return_value = SimpleNamespace(
        data=[{"id": recipe["id"]}]
    )
    with patch.object(recipe_service, "get_service_client", return_value=mock_client):
        rid = recipe_service.upsert_recipe(recipe)
    assert rid == recipe["id"]


def test_mock_recipe_items_reference_recipe():
    for item in MOCK_RECIPE_ITEMS:
        assert item["recipe_id"] == MOCK_RECIPES[0]["id"]
        assert item["ingredient_id"].startswith("ing-")
