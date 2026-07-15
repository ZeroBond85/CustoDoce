# `alert_service` — API

> Última atualização: 2026-07-15 16:13 UTC
> Gerado por AST parsing dos serviços em `services/alert_service.py`.

## Funções Públicas (4)

### check_price_drops(ingredient_id: str, current_price: float, history_prices: list[dict])

Check if the current price is a significant drop compared to history.

### get_active_alert_rules()

### get_alert_recipients(channel: str)

### process_proactive_alerts()

Core loop to check all active rules and notify recipients.
Should be called at the end of main.py.

