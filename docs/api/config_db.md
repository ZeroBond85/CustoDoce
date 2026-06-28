# Config DB API

Camada de acesso ao banco de dados para configurações. Substitui arquivos YAML por tabelas Supabase.

## Tabelas

- `ingredients` — 23 ingredientes canônicos com aliases e search_terms
- `stores` — 51 lojas (Tier 1-4) com scrapers e URLs
- `scrape_frequencies` — cronograma por loja (cron_expression, timezone, max_retries)
- `feature_flags` — flags globais (scrapers_enabled, quality_gates_enabled, etc.)
- `alert_rules` — regras de alerta (threshold, trigger, channel)
- `recipients` — canais de notificação (email, telegram)
- `schedules` — agendamentos de relatórios

## Ingredientes

### `get_all_ingredients(include_inactive=False) -> list[Ingredient]`

Lista todos os ingredientes. Por padrão só retorna ativos.

```python
from services.config_db import get_all_ingredients

ingredients = get_all_ingredients(include_inactive=True)
```

---

### `get_active_ingredients() -> list[Ingredient]`

Ingredientes com `active=True`.

---

### `get_ingredient_by_name(canonical_name) -> Optional[Ingredient]`

Busca por nome canônico.

---

### `upsert_ingredient(data) -> Ingredient`

Insere ou atualiza. Usa `canonical_name` como conflict target.

```python
from services.config_db import upsert_ingredient

upsert_ingredient({
    "canonical_name": "Leite Condensado",
    "category": "lacteos",
    "brands": ["Moça", "Piracanjuba"],
    "search_terms": ["leite condensado", "leite condensado integral"],
    "aliases": ["leite condensadoIntegral", "leite condensado祭"],
    "active": True,
})
```

---

### `delete_ingredient(ingredient_id)`

Remove ingrediente e todos os preços/histórico/review_items associados.

---

## Lojas

### `get_all_stores(include_inactive=False) -> list[Store]`

Lista todas as lojas com config de scraper.

```python
stores = get_all_stores(include_inactive=True)
for s in stores:
    print(f"{s['name']} (Tier {s['tier']}): {s['scraper']}")
```

---

### `get_store_by_name(name) -> Optional[Store]`

Busca loja por nome exato.

---

### `upsert_store(data) -> Store`

Insere ou atualiza loja.

```python
upsert_store({
    "name": "Assaí Santos",
    "tier": 1,
    "is_active": True,
    "scraper": "flyer",
    "base_url": "https://perfil.asisa.com.br/",
    "publish_day": "quarta",
})
```

---

## Frequências de Scraping

### `get_enabled_schedules() -> list`

Retorna schedules com `enabled=True`.

### `get_all_schedules(include_disabled=False) -> list`

---

## Feature Flags

### `get_all_feature_flags() -> dict`

Retorna dict com todas as flags `{flag_name: bool}`.

### `set_feature_flag(name, value) -> bool`

Ativa ou desativa uma flag.

Flags disponíveis: `scrapers_enabled`, `quality_gates_enabled`, `notifications_enabled`, `llm_fuzzy_matching`, `semantic_matching_enabled`, `auto_approve_high_confidence`.

---

## Alertas

### `get_enabled_alert_rules(trigger=None) -> list`

Regras de alerta ativas, opcionalmente filtradas por trigger.

Triggers: `no_price_48h`, `price_spike`, `new_store`, `weekly_summary`.

---

## Recipients

### `get_active_recipients(channel=None) -> list`

Canais ativos, filtrados por `channel` (email/telegram).

### `upsert_recipient(data) -> dict`

---

## Sync YAML → DB

### `sync_ingredients_from_yaml() -> dict`

Lê `config/ingredients.yaml` e faz upsert de todos os ingredientes no DB. Retorna `{added, updated, errors}`.

### `sync_stores_from_yaml() -> dict`

Lê `config/stores.yaml` e faz upsert de todas as lojas.

---

## Validação

```python
from services.config_db import get_all_ingredients, get_all_stores

assert len(get_all_ingredients()) == 23  # 23 ingredientes canônicos
assert len(get_all_stores()) == 51        # 51 lojas configuradas
```