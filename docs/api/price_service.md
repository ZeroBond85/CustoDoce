# Price Service API

Price Service é uma **facade** que expõe funções de `price_repository`, `review_queue_service`, `price_analytics` e `maintenance_service`.

## Configuração

```python
import os
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
```

## Preços

### `search_prices(ingredient, sort_by="price_per_kg", sort_order="asc", limit=100, valid_only=True)`

Busca preços por ingrediente com ordenação server-side.

**Parâmetros:**
| Nome | Tipo | Default | Descrição |
|------|------|---------|-----------|
| `ingredient` | `str` | — | Nome canônico do ingrediente |
| `sort_by` | `str` | `"price_per_kg"` | Campo de ordenação: `price_per_kg`, `created_at`, `raw_price` |
| `sort_order` | `str` | `"asc"` | `asc` ou `desc` |
| `limit` | `int` | `100` | Limite de resultados |
| `valid_only` | `bool` | `True` | Filtrar apenas preços com `is_valid=True` |

**Retorno:** `List[dict]` — lista de registros de preço com campos normalizados.

**Exemplo:**
```python
from services.price_service import search_prices

result = search_prices("Leite Condensado", sort_by="price_per_kg", sort_order="asc")
for item in result:
    print(f"{item['store_name']}: R${item['normalized']['price_per_kg']:.2f}/kg")
```

---

### `get_price_history(ingredient, days=30, valid_only=False)`

Histórico de preços de um ingrediente.

**Parâmetros:**
| Nome | Tipo | Default | Descrição |
|------|------|---------|-----------|
| `ingredient` | `str` | — | Nome canônico do ingrediente |
| `days` | `int` | `30` | Dias de histórico |
| `valid_only` | `bool` | `False` | Filtrar apenas válidos |

**Retorno:** `List[dict]` — séries temporais de preço por loja.

---

### `upsert_price(price_data: dict, use_rpc=True)`

Insere ou atualiza um preço. Usa RPC server-side para dedup.

**Parâmetros:**
| Nome | Tipo | Default | Descrição |
|------|------|---------|-----------|
| `price_data` | `dict` | — | Dados do preço (ver schema) |
| `use_rpc` | `bool` | `True` | Usar `upsert_price_rpc` vs INSERT direto |

**Campos requeridos em `price_data`:**
```python
{
    "store_id": "uuid",
    "ingredient_id": "uuid",
    "raw_price": 42.90,
    "raw_unit": "cx 12x395g",
    "product_name": "Leite Condensado Moça 12x395g",
    "brand": "Moça",          # opcional
    "match_type": "exato",    # opcional
    "match_confidence": 1.0,  # opcional
}
```

**Retorno:** `dict` — registro inserido/atualizado.

---

### `get_cheapest_prices(ingredient, top_n=3)`

Retorna os `top_n` preços mais baratos de um ingrediente.

**Parâmetros:**
| Nome | Tipo | Default | Descrição |
|------|------|---------|-----------|
| `ingredient` | `str` | — | Nome canônico |
| `top_n` | `int` | `3` | Quantidade de resultados |

**Retorno:** `List[dict]` — preços ordenados por `price_per_kg` ascendente.

---

## Review Queue

### `get_review_queue(limit=500)`

Retorna itens pendentes de revisão (match_confidence < 0.8).

**Retorno:** `List[dict]` — itens com `match_type`, `match_reason`, `top3_candidates`.

---

### `approve_review_item(item_id: str, ingredient_id: str, brand_override="")`

Aprova um item da review queue, inscrevendo-o como preço válido.

---

### `reject_review_item(item_id: str)`

Rejeita um item da review queue (marca como `rejected`).

---

## Analytics

### `get_longitudinal_winners(days=90)`

Ranking de lojas com mais vitórias por ingrediente no período.

**Retorno:** `List[dict]` — `{store_id, store_name, ingredient_id, wins, avg_price}`.

---

### `get_price_trends(ingredient, days=90)`

Tendência de preço (média móvel, mínima, máxima) por loja.

**Retorno:** `List[dict]` — `{store_id, store_name, trend_days[], min_ppk, max_ppk, avg_ppk}`.

---

### `get_cross_ingredient_ranking(days=90)`

Ranking transversal: menor preço médio por ingrediente no período.

---

## Manutenção

### `cleanup_old_prices(days=90)`

Remove preços duplicados ou inválidos mais antigos que `days`.

### `log_scraper_run(store_id, status, items_found=0, items_matched=0, error_message="")`

Registra execução de scraper na tabela `scraping_logs`.

---

## Schema RPC

### `upsert_price_rpc(price_data)`

Função server-side que faz upsert com dedup baseada em `store_id + ingredient_id + raw_unit + raw_price`. Garante idempotência mesmo com retries.

**Retorno:** `{id, inserted_at, updated_at}`.