# `price_analytics` — API

> Última atualização: 2026-07-10 22:11 UTC
> Gerado por AST parsing dos serviços em `services/price_analytics.py`.

## Funções Públicas (6)

### generate_report_html(products: list[PriceEntry], ingredients: list[Ingredient])

Generates the HTML report for daily emails.

### get_cross_ingredient_ranking(days: int)

### get_longitudinal_winners(days: int)

Identify stores that are consistently the cheapest over time.

### get_price_trends(ingredient_id: str, days: int)

### get_telegram_report(ingredients: list[Ingredient], top_n: int)

### otimizar_carrinho_compras(lista_itens: dict, max_sources: int)

Analisa a lista de compras e calcula os cenários Monofonte e Multifonte.

