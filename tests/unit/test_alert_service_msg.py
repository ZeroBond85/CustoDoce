"""Regressão: alerta de preço mostrava o nome da LOJA no campo "Ingrediente".

Bug de produção (2026-08-21): alert_service.py usava p['store_name'] no campo
"Ingrediente" da mensagem. Fix: usa ingredient_id (nome canônico) + adiciona
marca/endereço/validade quando disponíveis. Também elimina N+1 do histórico
(uma query .in_() para todos os ingredientes).
"""

from unittest.mock import MagicMock, patch

import services.alert_service as alerts


def _client(latest: list[dict], hist: list[dict], stores: list[dict]):
    client = MagicMock()

    def table(name):
        t = MagicMock()
        if name == "v_latest_prices":
            t.select.return_value.execute.return_value = MagicMock(data=latest)
        elif name == "price_history":
            t.select.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = (
                MagicMock(data=hist)
            )
        elif name == "stores":
            t.select.return_value.execute.return_value = MagicMock(data=stores)
        else:
            t.select.return_value.execute.return_value = MagicMock(data=[])
        return t

    client.table.side_effect = table
    return client


@patch("services.alert_service.get_alert_recipients", return_value=[{"target": "@test", "active": True}])
@patch("services.alert_service.send_telegram_message")
@patch("services.alert_service.get_supabase")
def test_alerta_usa_ingrediente_nao_loja(mock_gs, mock_send, mock_recips):
    latest = [
        {
            "ingredient_id": "Manteiga",
            "store_name": "Assaí Atacadista",
            "store_id": "assai",
            "price_per_kg": 30.0,
            "raw_product": "Manteiga com Sal Camil 500g",
            "brand": "Camil",
            "valid_until": "2026-08-30",
        }
    ]
    hist = [{"ingredient_id": "Manteiga", "normalized": {"price_per_kg": 40.0}}]
    mock_gs.return_value = _client(latest, hist * 2, [{"id": "assai", "address": "Av. Anna Costa, 340", "city": "Santos"}])
    mock_rules = [MagicMock()]
    mock_rules[0] = {"trigger": "price_drop", "channel": "telegram"}

    with patch("services.alert_service.get_active_alert_rules", return_value=[{"trigger": "price_drop", "channel": "telegram"}]):
        alerts.process_proactive_alerts()

    assert mock_send.called
    msg = mock_send.call_args[0][1]
    assert "Ingrediente: <b>Manteiga</b>" in msg
    assert "Ingrediente: Assaí" not in msg
    assert "Marca: Camil" in msg
    assert "📍 Av. Anna Costa, 340 — Santos" in msg
    assert "Válido até: 2026-08-30" in msg


@patch("services.alert_service.get_alert_recipients", return_value=[{"target": "@test", "active": True}])
@patch("services.alert_service.send_telegram_message")
@patch("services.alert_service.get_supabase")
def test_alerta_sem_marca_omitida(mock_gs, mock_send, mock_recips):
    latest = [
        {
            "ingredient_id": "Farinha de Trigo",
            "store_name": "X",
            "store_id": "",
            "price_per_kg": 3.0,
            "raw_product": "Farinha 1kg",
            "brand": "Desconhecido",
            "valid_until": None,
        }
    ]
    hist = [{"ingredient_id": "Farinha de Trigo", "normalized": {"price_per_kg": 5.0}}]
    mock_gs.return_value = _client(latest, hist * 2, [])

    with patch(
        "services.alert_service.get_active_alert_rules", return_value=[{"trigger": "price_drop", "channel": "telegram"}]
    ):
        alerts.process_proactive_alerts()

    msg = mock_send.call_args[0][1]
    assert "Marca:" not in msg


def test_check_price_drops_sem_historico():
    assert alerts.check_price_drops("Ing", 10.0, []) is None
