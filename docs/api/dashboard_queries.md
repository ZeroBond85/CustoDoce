# Dashboard Queries API

Funções de query para o dashboard Streamlit. Todas usam cache LRU e Supabase client.

## Configuração

```python
from services.dashboard_queries import (
    get_latest_prices_cached,
    get_prices_for_ingredient_cached,
)
```

## Preços (com cache)

### `get_latest_prices_cached(valid_only=True, limit=2000)`

Retorna preços mais recentes (view materializada `prices_latest`).

```python
prices = get_latest_prices_cached(valid_only=True, limit=5000)
```

---

### `get_prices_for_ingredient_cached(ingredient, valid_only=True)`

Busca preços por ingrediente (usa `search_prices` por baixo).

```python
prices = get_prices_for_ingredient_cached("Leite Condensado")
```

---

### `get_price_history_cached(ingredient, days=30, valid_only=False)`

Histórico cacheado.

---

### `get_cheapest_prices_cached(ingredient, top_n=3)`

Top N preços mais baratos (cache LRU 128 entries).

```python
cheapest = get_cheapest_prices_cached("Creme de Leite", top_n=5)
```

---

## Analytics

### `get_longitudinal_winners_cached(days=90)`

Ranking de lojas vencedoras por ingrediente no período.

### `get_price_trends_cached(ingredient, days=90)`

Tendência de preço (min, max, avg) por loja.

### `get_cross_ingredient_ranking_cached(days=90)`

Ranking transversal de preço médio por ingrediente.

---

## Scrapers / Logs

### `get_recent_scraper_logs(limit=50)`

Retorna logs recentes da tabela `scraping_logs`.

```python
logs = get_recent_scraper_logs(100)
```

---

### `get_store_health()`

Saúde por loja (últimas 200 execuções). Retorna dict com:
- `runs`, `errors`, `success_rate`
- `total_found`, `total_matched`
- `last_run`, `latencies[]`, `latency_p95_ms`

---

### `get_stores_with_frequencies()`

Stores com `scrape_frequency` (tier, scraper, is_active, cron_expression, timezone, max_retries).

---

## Cobertura

### `get_dashboard_kpis()`

KPIs agregados: `total_prices`, `ingredients_covered`, `stores_active`, `avg_price_per_kg`.

```python
kpis = get_dashboard_kpis()
```

---

### `get_coverage_by_ingredient()`

Cobertura por ingrediente: `{ingredient, store_count, prices, min_ppk, avg_ppk}`.

---

## Review Queue

### `get_review_queue_cached(limit=500)`

Itens pendentes de revisão.

### `approve_review_item_cached(item_id, ingredient_id, brand_override="")`

Aprova item (escreve via service client).

### `reject_review_item_cached(item_id)`

Rejeita item.

---

## Utilidades

### `extract_ppk(row) -> float`

Extrai `price_per_kg` de um row de preço normalizado.

### `extract_pun(row) -> float`

Extrai `price_per_un` de um row.

### `clear_all_caches()`

Limpa todos os LRU caches (usar após mutações de dados).