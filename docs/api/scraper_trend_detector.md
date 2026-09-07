# `scraper_trend_detector` — API

> Última atualização: 2026-09-07 13:21 UTC
> Gerado por AST parsing dos serviços em `services/scraper_trend_detector.py`.

## Funções Públicas (5)

### analyze_all_stores()

Analisa todas as lojas ativas e retorna lista ordenada por trend_score desc.

### analyze_store(store_name: str)

Analisa uma loja: busca logs, computa trend, retorna resultado.

### compute_trend_score(baseline_30d: list[dict[str, Any]], current_7d: list[dict[str, Any]])

Computa trend_score comparando janela atual (7d) vs baseline (30d).

### should_alert(store_name: str, cooldown_hours: float)

Verifica se a loja pode receber alerta (cooldown expirado ou primeiro alerta).

### update_alert_state(store_name: str, trend_score: float, status: str, active: bool)

Persiste estado do alerta para uma loja.

