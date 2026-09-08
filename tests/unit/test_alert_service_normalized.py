"""Testes da Regra #7 (AGENTS.md): `normalized` pode ser bool, sempre proteger.

check_price_drops acessa p["normalized"]["price_per_kg"]. Sem o guard
`isinstance(normalized, dict)`, um registro com `normalized: true` (bool)
estoura AttributeError/TypeError na iteração de preços históricos.
"""

import pytest

from services.alert_service import check_price_drops


def _hist(*entries):
    return [dict(e) for e in entries]


def test_bool_normalized_does_not_crash():
    """Registro com normalized=True (bool) não deve explodir o check."""
    history = _hist(
        {"ingredient_id": "X", "normalized": True},
        {"ingredient_id": "X", "normalized": {"price_per_kg": 12.0}},
    )
    # Sem o guard, `True` é truthy → p["normalized"]["price_per_kg"] lança TypeError.
    result = check_price_drops("X", current_price=10.0, history_prices=history)
    assert result is not None
    assert result["type"] == "price_drop"


def test_filters_out_non_dict_normalized():
    """Entradas com normalized bool/None/Missing são ignoradas do cálculo."""
    history = _hist(
        {"ingredient_id": "X", "normalized": True},
        {"ingredient_id": "X", "normalized": None},
        {"ingredient_id": "X"},
        {"ingredient_id": "X", "normalized": {"price_per_kg": 100.0}},
    )
    result = check_price_drops("X", current_price=20.0, history_prices=history)
    assert result is not None
    # Só a entrada com 100.0 entrar no cálculo → drop = (100-20)/100 = 80%.
    assert result["drop_pct"] == pytest.approx(80.0)


def test_no_valid_prices_returns_none():
    """Se nenhuma entrada tem price_per_kg válido (dict >0), retorna None."""
    history = _hist(
        {"ingredient_id": "X", "normalized": True},
        {"ingredient_id": "X", "normalized": {"price_per_kg": 0}},
    )
    assert check_price_drops("X", current_price=5.0, history_prices=history) is None


def test_empty_history_returns_none():
    assert check_price_drops("X", current_price=5.0, history_prices=[]) is None
