# `price_intelligence` — API

> Última atualização: 2026-07-15 11:58 UTC
> Gerado por AST parsing dos serviços em `services/price_intelligence.py`.

## Funções Públicas (3)

### detect_anomaly(self, ingredient_id: str, store_id: str, price_per_kg: float)

Detecta se um preço é anômalo.
Retorna: {is_anomaly, severity, tag, expected_range}

### enrich_prices(self, prices: list[dict])

Enriquece lista de preços com tags de inteligência.

### get_historical_stats(self, ingredient_id: str, store_id: str)

Retorna média, std, min, max do histórico de preços.

