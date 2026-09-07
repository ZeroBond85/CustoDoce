# `scraper_alert` — API

> Última atualização: 2026-09-07 13:21 UTC
> Gerado por AST parsing dos serviços em `services/scraper_alert.py`.

## Funções Públicas (4)

### notify_health_critical(scraper_name: str, health_score: int)

### notify_scraper_disabled(scraper_name: str, reason: str, failures_count: int)

### notify_scraper_recovered(scraper_name: str)

### send_trend_alert(store_name: str, trend: dict[str, Any])

Envia alerta de degradação/trend via Telegram (fallback email).

