# `price_repository` — API

> Última atualização: 2026-07-16 00:26 UTC
> Gerado por AST parsing dos serviços em `services/price_repository.py`.

## Funções Públicas (4)

### get_latest_prices(valid_only: bool, limit: int)

### get_price_history(ingredient_canonical: str, days: int, valid_only: bool)

### search_prices(ingredient_canonical: str, sort_by: str, sort_order: str, limit: int, tier: int | None, logistics: str | None, city: str | None, valid_only: bool)

### upsert_price(price_entry: PriceEntry)

