# Plano Único: Review Queue Cleanup + Bug Fixes Estruturais

## Ordem Lógica de Execução

### FASE 0 — Limpeza Imediata do Banco (imediato, 5min)
**O quê**: Deletar 247 itens de teste da `review_queue` (Test Review Queue Store, E2E Test Store, Test Store)

**Por que primeiro**: Remove o ruído visual, permite ver o estado real do banco, e não quebra nada.

**Verificação**: Contagem cai de 430 para ~183 itens

---

### FASE A — Bug Crítico: Commit Parcial no Approve (services/price_service.py)
**O quê**: Em `approve_review_item()`, o status é atualizado para "approved" ANTES de `upsert_price()` e `add_alias_to_ingredient()`. Se essas falharam, o item fica órfão.

**Correção**:
1. Mover `client.table("review_queue").update({status: "approved"})` para DEPOIS de `upsert_price()` + `add_alias_to_ingredient()` bem-sucedidos
2. Envolver cada etapa em try/except separado
3. Se falhar, retornar erro sem alterar o status

**Arquivos**: `services/price_service.py:265-355`

---

### FASE B — IndexError no Reject (services/price_service.py)
**O quê**: `reject_review_item()` faz `result.data[0]` sem verificar lista vazia

**Correção**:
1. Verificar `if not result.data: return {}`
2. Adicionar try/except básico

**Arquivos**: `services/price_service.py:357-365`

---

### FASE C — Cascade Deletes (services/config_db.py)
**O quê**: `delete_store()` e `delete_ingredient()` deixam órfãos em prices, price_history, review_queue, scraping_logs, flyers, scrape_frequencies

**Correção**: Antes do DELETE, limpar tabelas relacionadas

**Arquivos**: `services/config_db.py:55-58` e `127-130`

---

### FASE D — Filtro de Keywords no Matcher (PREVENÇÃO DE LIXO)
**O quê**: Produtos sem relação com os 23 ingredientes (ex: "Sabão em Pó") viram lixo na review_queue porque o fuzzy matcher scoreia 55-80% em tokens aleatórios

**Correção em `parsers/matcher.py`**:
1. Criar `extract_all_keywords(ingredients)` → set com search_terms + aliases + canonical_names
2. Criar `has_ingredient_keyword(product_text, keyword_set)` → True se alguma palavra do produto estiver no set

**Correção em `main.py:process_price_match()`**:
1. Antes de `match_ingredient()`, verificar `has_ingredient_keyword()`
2. Se False → `return None` (ignora produto)

---

### FASE E — Cleanup Periódico (main.py)
**O quê**: Itens velhos com baixa confiança acumulam na fila

**Correção**:
1. Adicionar `auto_reject_stale_review_items(max_age_days=7, min_confidence=60)` em `main.py`
2. Chamar no loop de cleanup junto com `cleanup_old_prices`, `cleanup_old_logs`, `cleanup_old_flyers`

---

### FASE F — UX: Confirmação nos Botões (admin/app.py)
**O quê**: Aprovar e Rejeitar executam com clique único, sem confirmação

**Correção**: Adicionar padrão `st.session_state` 2-step (igual schedules/recipients):
1. Primeiro clique: "Confirmar aprovação?" com "Sim" / "Cancelar"
2. Segundo clique: executa ação

---

### FASE G — UI: Botão Excluir Alert Rule (admin/app.py)
**O quê**: `delete_alert_rule()` existe em `config_db.py` mas nunca foi importado no dashboard

**Correção**:
1. Importar `delete_alert_rule` em `admin/app.py:43`
2. Adicionar botão Excluir no renderer de alert rules

---

### FASE H — Verificação Final
1. `ruff check .`
2. `bandit -r services/ admin/ -x tests/`
3. `python -m pytest tests/ -q`
4. Teste comportamental na base real (insert + assert via REST API)

---

## Sumário de Arquivos Alterados

| Arquivo | Fases |
|---|---|
| `services/price_service.py` | A, B |
| `services/config_db.py` | C, G (import) |
| `parsers/matcher.py` | D |
| `main.py` | D, E |
| `admin/app.py` | F, G |

## Duração Estimada
- FASE 0: 5min
- FASE A: 15min
- FASE B: 5min
- FASE C: 15min
- FASE D: 20min
- FASE E: 10min
- FASE F: 15min
- FASE G: 10min
- FASE H: 5min
- **Total**: ~1h40
