# Guia: Adicionando Novos Ingredientes

## Visão Geral

O sistema suporta três formas de adicionar/atualizar ingredientes, todas convergindo para a tabela `ingredients` do Supabase (runtime source of truth).

## 1. Via YAML (config/ingredients.yaml) — Fonte de Verdade Versionada

```yaml
- canonical: "Novo Ingrediente"
  category: "categoria"      # Valores DB: acucares, chocolates, confeitos, lacteos, ovos, pastas, secos, temperos, farinhas, essencias
  match_threshold: 0.80      # OBRIGATÓRIO - 0.75=tolerante, 0.80=padrão, 0.85=estrito
  unit_target: "kg"
  brands: ["Marca1"]
  search_terms: ["termo1"]
  aliases: ["Alias 1"]
  exclude_terms: ["excluir1"]
  active: true
```

**Validação**: `python scripts/sync_ingredient_fields.py --dry-run` detecta `match_threshold` ausente.

**Thresholds recomendados**:
- **0.85 (estrito)**: Chocolates (% cacau crítico), Gotas (tipo crítico)
- **0.75 (tolerante)**: Leites ("condensado"/"condens"), Granulados, Top Confete
- **0.80 (padrão)**: Açúcares, Creme de Avelã, Coco, Farinha, Micro Ball, Manteiga, Fermento, Baunilha, Ovos, Flor de Sal

## 2. Via Dashboard (ingredientes.py → aba "Novo")

- Form inclui: Threshold (NumberColumn 0.0-1.0 step 0.01), Excluir (TextColumn), categorias sincronizadas com DB
- Validação no submit: canonical único, threshold 0.0-1.0
- Salva no YAML e upserta no DB automaticamente

## 3. Via Código (programático)

```python
from services.config_db import upsert_ingredient
upsert_ingredient({
    "canonical_name": "Novo",
    "category": "categoria",
    "match_threshold": 0.80,  # opcional - default 0.80
    ...
})
```

## Sync Automático (YAML ↔ DB)

```bash
# YAML → DB (após editar YAML)
python scripts/sync_ingredient_fields.py --execute
python scripts/sync_ingredient_fields.py --dry-run  # Verifica 0 diffs
```

**Comportamento**:
- `exclude_terms`, `match_threshold`: YAML → DB (exact, YAML wins)
- `search_terms`, `brands`: YAML ∪ DB (merge, preserva enriquecimento manual)
- `aliases`: Gerenciado no Dashboard, limpo de artifacts de teste no sync

## Feedback Loop Automatizado

```bash
# Extrai aliases confirmados do match_feedback
python scripts/ingest_match_feedback_aliases.py
# Roda automaticamente no pipeline de scrape (após cada execução)
```

## Extensibilidade Futura

- Novos campos em `ingredients.yaml` → adicionar a `_SYNC_EXACT` ou `_SYNC_MERGE` em `sync_ingredient_fields.py`
- Novas categorias → adicionar a `CANONICAL_CATEGORIES` em `dashboard/pages/ingredientes.py`
- Novos thresholds → documentar nesta tabela