# CustoDoce - Análise Completa de UX & Plano de Testes

**Data**: 2026-08-08 | **Versão**: 1.0 | **Sprint**: 17 (Pós-Otimização Performance)

---

## Sumário Executivo

O dashboard CustoDoce possui **21 páginas** organizadas em 5 grupos funcionais, construído sobre Streamlit 1.58+ com `st.navigation()` nativo. A arquitetura é modular (`dashboard/pages/*.py` + `dashboard/components/` + `services/dashboard_queries.py`).

### Pontos Fortes
- ✅ **Arquitetura limpa**: Single source of truth (`navigation_config.py`) para navegação
- ✅ **Componentes reutilizáveis**: KPI cards, data tables, dialogs, badges consistentes
- ✅ **CSS customizado**: Tema coeso (Nunito, paleta laranja/rosa), responsive breakpoints 640/768/1024px
- ✅ **Cache inteligente**: `@st.cache_data(ttl=300)` + `clear_all_caches()` para invalidate
- ✅ **Acessibilidade base**: Skip link, focus visible, reduced motion, badges semânticos
- ✅ **Testes E2E reais**: Playwright contra cloud + local, visual regression, supabase checks

### Gaps Críticos Identificados

| Área | Severidade | Descrição |
|------|------------|-----------|
| **Mobile UX** | 🔴 Crítico | Sidebar gradient impede leitura em mobile; tabelas sem sticky header consistente |
| **Performance** | 🟡 Alto | `visao_geral.py` faz 5 queries sequenciais; `insights.py` recalcula outliers no frontend |
| **Formulários** | 🟡 Alto | `label_visibility="collapsed"` em `calculadora.py:39` viola a11y; `st.selectbox` sem help text |
| **Feedback** | 🟡 Alto | Actions sem loading states (ex: `revisao.py` approve/reject); toast messages inconsistentes |
| **Error Handling** | 🟡 Alto | Try/except genéricos; erros Supabase não surfam para UI amigável |
| **Consistência Visual** | 🟢 Médio | Mix de `st.metric` vs `kpi_card`; tabs vs radio; ícones emojis vs semantic |
| **Keyboard Nav** | 🟢 Médio | Skip link existe mas foco não salta para conteúdo principal em algumas páginas |

---

## Análise Página por Página (21 Páginas)

### 📊 Painel (4 páginas)

#### 1. `visao_geral.py` — Landing Page
**Funcionalidades**: KPIs (4 métricas), Promoções ativas, Cobertura por ingrediente, Ranking longitudinal (gráfico Plotly), Ranking cruzado (top 3/ingrediente)

| Checklist | Status | Observações |
|-----------|--------|-------------|
| Carregamento inicial < 3s | ⚠️ | 5 queries sequenciais (`get_latest_prices_cached` + 4 cached helpers) |
| KPIs responsivos (1/2/4 cols) | ✅ | `.cd-kpi-row` CSS grid mobile-first |
| Promoções: empty state | ✅ | `info_box()` |
| Gráfico Plotly: mobile height | ⚠️ | `height=500` fixo; deve ser responsivo |
| Tabelas: overflow horizontal | ✅ | CSS `overflow-x: auto` global |
| Acessibilidade: labels | ❌ | `st.metric` sem `help`; `st.dataframe` sem `help` descritivo |
| Loading states | ✅ | `st.spinner` em queries pesadas |
| Error boundary | ❌ | Falha em uma query quebra página inteira |

**Melhorias**:
- Unificar queries em `_single_pass_prices()` (já existe em `dashboard_queries.py` — usar!)
- Adicionar `st.fragment` para KPIs independentes
- Gráfico: `config={'responsive': True}` + `use_container_width=True`

---

#### 2. `precos.py` — Consulta de Preços
**Funcionalidades**: Filtros (ingrediente, loja, tier), Tabela com R$/kg, R$/un, marca, promoção, frescor, deep-link via `query_params`

| Checklist | Status | Observações |
|-----------|--------|-------------|
| Filtros server-side (ingrediente + tier) | ✅ | `get_prices_for_ingredient_cached` |
| Filtro loja client-side | ✅ | Dataset já reduzido |
| Deep-link (`?ingredient=X&store=Y`) | ✅ | `_sync_query_params` / `_push_query_params` |
| Coluna "Frescor" com badge | ✅ | `freshness_column()` → HTML badge |
| Ordenação por R$/kg | ✅ | `sort_values("price_per_kg")` |
| Empty state | ✅ | `st.info("Nenhum preço encontrado.")` |
| A11y: selectbox labels | ❌ | `label_visibility="collapsed"` NÃO usado ✅ (tem label visível) |
| A11y: help text | ⚠️ | Frescor tem `help`, outros não |
| Mobile: tabela scroll | ✅ | CSS global |
| Performance: 5000 rows max | ✅ | Limit server-side |

**Melhorias**:
- Adicionar `help` em todos `column_config`
- Paginação nativa `st.pagination` se >100 rows
- Export CSV button

---

#### 3. `historico.py` — Histórico de Preços
**Funcionalidades**: Select ingrediente + período (7-365d), checkbox "válidos", 4 tipos gráfico (Linha/Área/Barras/Dispersão), Estatísticas por loja, Detalhamento tabela

| Checklist | Status | Observações |
|-----------|--------|-------------|
| Deep-link completo | ✅ | 4 params sincronizados |
| Gráficos Plotly responsivos | ⚠️ | `height=500` fixo |
| Estatísticas agg (mean/min/max/std/count) | ✅ | `groupby().agg()` |
| Tabela detalhada com todas cols | ✅ | 11 colunas renomeadas PT-BR |
| A11y: chart accessibility | ❌ | Plotly sem `config={'staticPlot': False}` + descrição textual |
| Mobile: chart height | ❌ | 500px quebra em <640px |
| Loading state | ✅ | `st.spinner` |
| Error: empty history | ✅ | `st.info` / `st.warning` |

**Melhorias**:
- `fig.update_layout(height=None)` + `use_container_width=True`
- Adicionar `st.caption` com resumo textual do gráfico (screen readers)
- `st.fragment` para gráfico isolado

---

#### 4. `promocoes.py` — Promoções em Destaque
**Funcionalidades**: Filtros multiselect (loja, ingrediente), Ordenação (R$/kg, economia, recentes), KPIs (count, avg R$/kg, última coleta), Tabela paginada

| Checklist | Status | Observações |
|-----------|--------|-------------|
| Filtros multiselect | ✅ | `st.multiselect` |
| KPIs row | ✅ | 3 colunas `st.metric` |
| Ordenação dinâmica | ✅ | `sort_values` |
| Empty state filtrado | ✅ | `st.warning` |
| A11y: multiselect label | ✅ | Label visível |
| Mobile: KPIs stack | ⚠️ | 3 cols → 1 col no CSS? Verificar |
| Performance: 500 limit | ✅ | `get_all_current_prices(limit=500)` |

**Melhorias**:
- Adicionar `st.pagination` (25/page)
- Badge visual "PROMO" na coluna `is_promotion`
- Export para CSV

---

### 📈 Análises (6 páginas)

#### 5. `insights.py` — Insights & Análises
**Funcionalidades**: Heatmap cobertura vs preço médio (bar horizontal), Outliers (z-score > 2), Top 10 melhores ofertas

| Checklist | Status | Observações |
|-----------|--------|-------------|
| Heatmap responsivo | ⚠️ | `orientation="h"` mas `height` não definido |
| Outliers: cálculo frontend | 🔴 | **Anti-pattern**: z-score calculado no Python loop sobre 5000 rows |
| Top 10 ofertas | ✅ | `nsmallest(10, "ppk")` |
| A11y: chart descriptions | ❌ | Ausente |
| Performance: outlier loop | 🔴 | O(n) Python no render — mover para SQL/RPC |
| Empty states | ✅ | `st.info` |

**Melhorias CRÍTICAS**:
- **Mover outlier detection para DB**: `CREATE OR REPLACE FUNCTION detect_outliers() RETURNS TABLE...`
- Usar `_coverage_from_prices` (já cached) — não recalcular
- Adicionar `st.fragment` para cada seção independente

---

#### 6. `fontes.py` — Fontes de Dados
**Funcionalidades**: Cobertura por ingrediente (tabela + bar chart), Promoções ativas, Ranking de fontes (lojas ativas com frequência)

| Checklist | Status | Observações |
|-----------|--------|-------------|
| Reutiliza `get_latest_prices_cached` | ✅ | Single query para cobertura + promoções |
| Bar chart horizontal | ✅ | `orientation="h"` |
| Ranking fontes | ✅ | `get_stores_with_frequencies()` |
| A11y: tabelas | ⚠️ | Sem `help` descritivo |
| Mobile: chart | ⚠️ | Height fixo implícito |

---

#### 7. `ranking.py` — Ranking de Preços (3 tabs)
**Funcionalidades**: 
- Tab 1: Vencedores Históricos (slider dias, bar chart)
- Tab 2: Tendências (select ingrediente + slider, line chart com min/max)
- Tab 3: Ranking Cruzado (slider dias, bar horizontal top 20)

| Checklist | Status | Observações |
|-----------|--------|-------------|
| Tabs nativas `st.tabs` | ✅ | 3 tabs funcionais |
| Sliders com key única | ✅ | `key="trend_days"`, `key="cross_days"` |
| Gráficos Plotly | ⚠️ | Heights fixos, sem config responsivo |
| Deep-link | ❌ | Tabs não sincronizam `query_params` |
| A11y: tab panels | ✅ | Streamlit nativo gerencia ARIA |
| Cache: `cached_get_active_ingredients` | ✅ | Reutilizado |

**Melhorias**:
- Sincronizar tab ativa + sliders com `query_params`
- `st.fragment` por tab

---

#### 8. `calculadora.py` — Calculadora de Receitas (3 tabs)
**Funcionalidades**: 
- Tab 0: Modo Simples (ingredientes + qtd, auto-fill menor preço, salvar receita)
- Tab 1: Modo Completo (top 3 lojas por ingrediente, 3 cenários: melhor/médio/pior)
- Tab 2: Receitas Salvas (CRUD via Supabase direto)

| Checklist | Status | Observações |
|-----------|--------|-------------|
| **A11y: `label_visibility="collapsed"`** | 🔴 **VIOLAÇÃO** | Linha 39: `st.selectbox(..., label_visibility="collapsed")` — sem label visível |
| Formulários `st.form` | ✅ | Submit buttons claros |
| Session state para ingredientes | ✅ | `simple_ingredients`, `full_ingredients` |
| Auto-fill preços | ✅ | `get_cheapest_prices_cached(top_n=1/3)` |
| Cenários calculados | ✅ | 3 cenários com métricas |
| Salvamento DB | ✅ | `upsert_recipe` + `upsert_recipe_item` |
| Tab 2: Supabase direto | ⚠️ | `get_supabase()` no page — deveria usar `dashboard_queries` |
| Mobile: forms stack | ⚠️ | `st.columns([3,1])` — verificar CSS |
| Deep-link tab | ✅ | `calc_tab` em `query_params` |

**Melhorias CRÍTICAS**:
- **Corrigir linha 39**: Remover `label_visibility="collapsed"`, adicionar label visível + `help`
- Mover query Supabase direto para `dashboard_queries.py`
- Adicionar validação: `quantity_g > 0`, `yield_qty > 0`
- Toast de sucesso/erro em vez de `st.success`/`st.error` (persistem no rerun)

---

#### 9. `revisao.py` — Fila de Revisão
**Funcionalidades**: Lista itens confiança <80%, Filtros (confiança min, match_type), Card por item (imagem, dados, top 3 candidatos, diagnóstico), Ações: Aprovar (select ingrediente + brand override), Rejeitar, Adicionar Alias

| Checklist | Status | Observações |
|-----------|--------|-------------|
| Layout 2 colunas (imagem + dados) | ✅ | `st.columns([1,3])` |
| Progress bar confiança | ✅ | `st.progress(conf, text=...)` |
| Badge match_type colorido | ✅ | Emoji + cor |
| Expanders: top 3 + diagnóstico | ✅ | `st.expander` |
| Aprovação: select ingrediente sugerido | ✅ | `default_idx` pré-selecionado |
| Brand override | ✅ | Selectbox com opção "manter auto" |
| Rejeição: 1 click | ✅ | `reject_review_item_cached` |
| **Alias: funcionalidade stub** | 🔴 **INCOMPLETO** | Linha 166: `st.info("Funcionalidade: adicionar como alias...")` |
| Empty state | ✅ | `st.success("Fila vazia!")` |
| A11y: progress bar | ✅ | Semantic `progress` |
| A11y: image alt text | ❌ | `st.image` sem `caption` descritivo |
| Mobile: card stack | ⚠️ | 2 cols → 1 col? |
| Performance: 500 limit | ✅ | `get_review_queue_cached(limit=500)` |

**Melhorias**:
- **Implementar "Adicionar como Alias"**: chamar `add_alias_to_ingredient(suggested, raw_product)`
- Adicionar `caption` em `st.image` com descrição do produto
- `st.dialog` para confirmação de rejeição (destrutivo)
- Paginação se >50 itens

---

#### 10. `capacity_planning.py` — Capacity Planning
**Funcionalidades**: 3 métricas (Disco Supabase, GitHub Actions min, SMTP 24h) com progress bars, Ações de mitigação expandidas

| Checklist | Status | Observações |
|-----------|--------|-------------|
| KPIs com delta_color | ✅ | `inverse` para alertas |
| Progress bars coloridas | ✅ | Verde/amarelo/vermelho por threshold |
| Expander mitigações | ✅ | Markdown com links |
| **SMTP: proxy via scraping_logs** | 🔴 **IMPRECISO** | Linha 77: usa scraping_logs como proxy — precisa tabela `email_logs` real |
| A11y: metric labels | ✅ | Labels descritivas |
| Mobile: 3 cols stack | ✅ | CSS `.cd-kpi-row` gerencia |

---

### 📦 Cadastros (4 páginas)

#### 11. `lojas.py` — Gerenciamento de Lojas (3 tabs)
**Funcionalidades**: Tab 0: Lista + agendamentos; Tab 1: Form add/edit (14 campos + JSON selectors); Tab 2: Pendentes (integrado de `lojas_pendentes`)

| Checklist | Status | Observações |
|-----------|--------|-------------|
| Form completo 14 campos | ✅ | `st.form` com validação JSON |
| Selectors JSON textarea | ⚠️ | Usuário digita JSON manual — error-prone |
| Scraper selectbox: 15 opções | ✅ | Lista hardcoded |
| Tab 2: duplicate de `lojas_pendentes` | 🟡 **DRIFT** | Mesma lógica em 2 páginas |
| A11y: form labels | ✅ | Todos inputs têm label |
| JSON validation | ⚠️ | `json.loads` no submit — erro só no submit |
| Mobile: form fields stack | ✅ | `st.columns(2)` → CSS stack |

**Melhorias**:
- **Unificar Tab 2 com `lojas_pendentes.py`** (remover duplicação)
- JSON editor: usar `st.json` + `st.text_area` com validação live
- Scraper options: mover para config/constants

---

#### 12. `lojas_pendentes.py` — Lojas Pendentes
**Funcionalidades**: Lista pendentes (métricas: total, com endereço, casadas), Cards com ações: Aprovar+Casar, Rejeitar, ou (se não casada) Casar com existente / Criar nova / Rejeitar, Seção aprovadas (auto-promovidas)

| Checklist | Status | Observações |
|-----------|--------|-------------|
| Cards com progress match_score | ✅ | `st.progress(match_score, text=...)` |
| Ações contextuais (casada vs nova) | ✅ | Lógica condicional clara |
| Selectbox target store | ✅ | `get_active_stores()` |
| **Criar nova loja: stub** | 🔴 **INCOMPLETO** | Linha 110: `st.info("Funcionalidade: Criar nova loja...")` |
| Empty states | ✅ | `st.success` / `st.info` |
| A11y: buttons | ✅ | Labels claras |
| Mobile: card layout | ⚠️ | Verificar stack |

**Melhorias**:
- **Implementar "Criar Nova Loja"**: chamar `upsert_store` + aprovar
- Remover duplicação com `lojas.py` Tab 2

---

#### 13. `ingredientes.py` — Ingredientes (5 tabs)
**Funcionalidades**: Tab 0: Lista (filtros categoria/status); Tab 1: Add/Edit (form + dialog confirmação YAML + backup automático); Tab 2: Test Normalizer; Tab 3: Test Matcher; Tab 4: Sugerir Aliases (auto + botão add)

| Checklist | Status | Observações |
|-----------|--------|-------------|
| **YAML + DB sync com backup** | ✅ | `_backup_yaml()` + `upsert_ingredient` + dialog confirmação |
| Dialog nativo `st.dialog` | ✅ | Sprint 7 pattern |
| Test Normalizer/Matcher inline | ✅ | Útil para debug |
| Sugerir aliases: heurísticas | ✅ | Remove acentos, sinônimos, brands |
| **A11y: Tab 1 form labels** | ✅ | Todos visíveis |
| **A11y: Tab 4 button keys** | ⚠️ | `key=f"add_alias_{s}"` — `s` pode ter chars especiais |
| Mobile: tabs | ✅ | Streamlit nativo |
| YAML path hardcoded | ⚠️ | `Path("config/ingredients.yaml")` — deveria vir de config |

**Melhorias**:
- Sanitizar keys: `key=f"add_alias_{hash(s)}"`
- Mover YAML path para `services/config.py`
- Adicionar validação: `canonical_name` único

---

#### 14. `lojas_registro.py` (alias para `lojas_pendentes.py`)
**Nota**: Mesmo page_id mapeado para mesma função em `navigation_config.py:51`. **Remover do MENU_GROUPS** — duplicação.

---

### 🤖 Operações (6 páginas)

#### 15. `alertas.py` — Alertas e Regras (3 tabs)
**Funcionalidades**: Tab 0: Regras paginadas (25/page, `st.pagination` nativo), enable/disable all; Tab 1: Nova regra (form); Tab 2: Destinatários (CRUD)

| Checklist | Status | Observações |
|-----------|--------|-------------|
| **Pagination nativa** | ✅ | `st.pagination(num_pages, bind="query-params")` — Sprint 8 |
| Fallback manual pagination | ✅ | `_fallback_pagination` para <1.58 |
| Enable/disable all buttons | ✅ | Loop + `upsert_alert_rule` |
| Form nova regra | ✅ | Trigger selectbox (5 tipos), threshold, comparison |
| Destinatários multiselect | ✅ | Email + Telegram combinados |
| Batch form destinatários | ✅ | Tab 2 em `config.py` também — **duplicação** |
| A11y: pagination | ✅ | Streamlit nativo |
| Mobile: table scroll | ✅ | CSS global |

**Melhorias**:
- **Unificar destinatários** com `config.py` Tab 2
- Adicionar `help` em cada trigger type
- Validação: `threshold > 0` se comparison não vazio

---

#### 16. `scrapers.py` — Scrapers & Coleta (3 tabs)
**Funcionalidades**: Tab 0: Logs recentes (100) + Health por loja (error_rate); Tab 1: Agendamentos (tabela editável view-only); Tab 2: Health check manual (roda script externo)

| Checklist | Status | Observações |
|-----------|--------|-------------|
| JSONB sanitization | ✅ | `_sanitize_df_for_display` (Lição #51) |
| Health: error_rate calc | ✅ | `errors/runs` |
| Agendamentos: cron examples | ✅ | Info box com patterns |
| Health check manual | ⚠️ | Roda `scripts/store_health_check.main()` — bloqueia UI |
| A11y: tables | ⚠️ | Sem `help` |
| Mobile: tables | ✅ | Overflow horizontal |

**Melhorias**:
- Health check: `st.button` → `st.toast` + background task (não bloquear)
- Adicionar `st.pagination` nos logs (100 rows)
- Tab 1: tornar editável (inline edit → save)

---

#### 17. `scraper_health.py` — Scraper Health Dashboard (4 tabs)
**Funcionalidades**: Tab 0: Health overview (KPIs: healthy/degraded/critical, tabela com success_rate, latency_p95, avg_items); Tab 1: Cobertura lojas (stale >3d, days_since_price); Tab 2: Latency P95 bar chart (colorido por success_rate); Tab 3: Raw logs

| Checklist | Status | Observações |
|-----------|--------|-------------|
| KPI row 4 cols | ✅ | Healthy/Degraded/Critical/Total |
| Banner cobertura stale | ✅ | Error/success condicional |
| Tabela: formatação % e segundos | ✅ | `apply(lambda)` |
| Bar chart Plotly colorido | ✅ | Green/yellow/red por success_rate |
| Cobertura: days_since_price | ✅ | "nunca" para None |
| JSONB sanitization logs | ✅ | Mesmo helper |
| A11y: chart | ❌ | Sem descrição textual |
| Mobile: KPIs stack | ✅ | CSS |
| Mobile: bar chart | ⚠️ | Height fixo |

**Melhorias**:
- Adicionar descrição textual do gráfico latency (screen readers)
- `st.fragment` por tab
- Export CSV saúde

---

#### 18. `relatorios.py` — Relatórios & Alertas (3 tabs)
**Funcionalidades**: Tab 0: Builder (tipo, checkboxes, destinatários multiselect, canais); Tab 1: Preview HTML (iframe); Tab 2: Testar SMTP/Telegram

| Checklist | Status | Observações |
|-----------|--------|-------------|
| **Dialog confirmação envio** | ✅ | `st.dialog` com preview destinatários |
| Preview HTML iframe | ✅ | `st.components.v1.html(height=600)` |
| Test SMTP/Telegram buttons | ✅ | `test_smtp_connection()`, `test_telegram_connection()` |
| HTML report builder | ✅ | `build_daily_report_html()` + `build_telegram_summary()` |
| Destinatários: fallback chain | ✅ | ENV > YAML > manual |
| A11y: iframe | ❌ | `st.components.v1.html` sem `title` atributo |
| Mobile: builder form | ⚠️ | `st.columns(2)` stack? |
| Loading states | ✅ | `st.spinner` |

**Melhorias**:
- Adicionar `title="Relatório CustoDoce"` no iframe
- Toast notifications em vez de `st.success` persistente
- Agendamento de relatórios (cron)

---

#### 19. `flyers.py` — Panfletos (Flyers)
**Funcionalidades**: Grid 4 cols (thumbnails), Filtros (dias, fonte), Click → detalhes (imagem full + meta), Delete com `st.dialog` confirmação

| Checklist | Status | Observações |
|-----------|--------|-------------|
| **Grid CSS `.cd-flyer-grid`** | ✅ | Responsive: 1/2/auto-fill cols |
| **Dialog confirmação delete** | ✅ | Sprint 7 pattern |
| Thumbnail error handling | ✅ | Try/except + caption |
| Detalhes: col 3/1 split | ✅ | Imagem + meta |
| A11y: grid images | ❌ | `st.image` sem `caption` descritivo |
| Mobile: grid 1 col | ✅ | CSS `@media (max-width: 640px)` |
| Empty state | ✅ | `st.info` |

**Melhorias**:
- Adicionar `caption` em thumbnails: `st.image(url, caption=f"{store} - {date}")`
- Paginação se >20 flyers
- Bulk delete (checkbox + ação)

---

#### 20. `config.py` — Configuração do Sistema (4 tabs)
**Funcionalidades**: Tab 0: Feature Flags (batch form toggle all + save); Tab 1: Alert Rules (batch form + per-rule expander+form); Tab 2: Destinatários (batch form); Tab 3: Recarregar config + JSON view

| Checklist | Status | Observações |
|-----------|--------|-------------|
| **Batch forms** | ✅ | "Salvar Tudo" + "Reverter" — excelente UX |
| Per-rule expander+form | ✅ | Edição inline |
| **Destinatários: duplicado com `alertas.py`** | 🟡 **DRIFT** | Mesma funcionalidade em 2 páginas |
| Recarregar config | ✅ | `reload_config()` + safe JSON view |
| A11y: checkboxes | ✅ | Labels visíveis |
| Mobile: forms stack | ✅ | CSS |
| Secrets warning | ✅ | Info box explicando .env/Secrets |

**Melhorias**:
- **Remover Tab 2 (Destinatários)** — manter só em `alertas.py`
- Adicionar validação: feature flag key unique
- Toast ao salvar batch

---

#### 21. `diagnostico.py` — Diagnóstico do Sistema (4 tabs)
**Funcionalidades**: Tab 0: Benchmarks (cold/warm cache, stores, ingredients load); Tab 1: Conectividade (Supabase, SMTP, Telegram buttons); Tab 2: Integridade (orphan prices, distribuição, review queue count); Tab 3: Capacity Planning (embed de `capacity_planning.py`)

| Checklist | Status | Observações |
|-----------|--------|-------------|
| Benchmarks automatizados | ✅ | `time.perf_counter()` + `clear_all_caches()` |
| Conectividade: 3 buttons | ✅ | Testes reais |
| Integridade: orphan check | ✅ | Supabase query direta |
| Capacity embed | ✅ | Reutiliza função |
| A11y: buttons | ✅ | Labels claras |
| Mobile: tabs | ✅ | Nativo |
| **Supabase direto no page** | 🟡 | Deveria usar `dashboard_queries` |

**Melhorias**:
- Mover queries Supabase para `dashboard_queries.py`
- Adicionar `st.toast` resultados
- Export relatório diagnóstico

---

#### 22. `ci_telemetry.py` — CI Telemetria
**Funcionalidades**: KPIs (total, limite, restante, última atualização), Progress bar, Tabela workflows (minutos, %, status), Tendência histórica (placeholder), Botão refresh

| Checklist | Status | Observações |
|-----------|--------|-------------|
| KPIs 4 cols | ✅ | `delta_color="inverse"` |
| Progress bar uso | ✅ | `min(pct/100, 1.0)` |
| Workflows table | ✅ | Sort desc, status colorido |
| **Dados: arquivo JSON local** | ⚠️ | `.github/minutes_report.json` — precisa script CI para gerar |
| Refresh button | ✅ | `st.rerun()` |
| Mobile: KPIs stack | ✅ | CSS |
| A11y: table | ⚠️ | Sem `help` |

**Melhorias**:
- Documentar geração do `minutes_report.json` no CI
- Gráfico tendência histórica (quando houver dados)
- Alertas visuais se >80% uso

---

## Análise de Acessibilidade (WCAG 2.1 AA)

### ✅ Conformes
- Skip link funcional (`.skip-link` CSS + `render_skip_link()`)
- Focus visible em buttons, selects, checkboxes (outline laranja 2px)
- Reduced motion respeitado (`@media (prefers-reduced-motion: reduce)`)
- Color contrast: texto #2D2D2D sobre #FAF9F6 = 14.5:1 (AAA)
- Badges semânticos (success/warning/danger/neutral)
- `st.tabs` / `st.dialog` / `st.pagination` nativos gerenciam ARIA

### ❌ Violações
| Página | Linha | Violação | WCAG |
|--------|-------|----------|------|
| `calculadora.py` | 39 | `label_visibility="collapsed"` sem caption visível | 1.3.1, 3.3.2 |
| `revisao.py` | 77 | `st.image` sem `caption` / alt text | 1.1.1 |
| `flyers.py` | 62 | `st.image` sem `caption` | 1.1.1 |
| `relatorios.py` | 141 | `st.components.v1.html` sem `title` | 4.1.2 |
| Múltiplas | - | `st.dataframe` sem `help` descritivo | 1.3.1 |
| Múltiplas | - | Plotly charts sem descrição textual | 1.1.1 |

### 🟡 Parciais
- Form labels: maioria OK, mas `calculadora.py` viola
- Error messages: genéricos ("Erro ao salvar") — deveria ser específico
- Keyboard nav: Tab order OK, mas skip link target `#main-content` não existe em todas pages

---

## Análise de Responsividade (Mobile-First)

### Breakpoints CSS Ativos
```css
@media (max-width: 640px)   { /* Mobile: 1 col KPIs, 1 col grid, stack forms */ }
@media (max-width: 768px)   { /* Tablet: 2 col KPIs, 2 col flyer grid */ }
@media (min-width: 1025px)  { /* Desktop: 4 col KPIs, auto-fill flyer grid */ }
```

### Problemas por Página

| Página | Mobile | Tablet | Desktop | Ação |
|--------|--------|--------|---------|------|
| `visao_geral` | ✅ KPIs 1 col | ✅ 2 cols | ✅ 4 cols | Gráfico height responsivo |
| `precos` | ✅ Tabela scroll | ✅ | ✅ | - |
| `historico` | ❌ Chart 500px | ❌ Chart 500px | ✅ | `height=None` + `use_container_width` |
| `promocoes` | ⚠️ KPIs 3 cols? | ✅ | ✅ | Verificar CSS `.cd-kpi-row` |
| `insights` | ❌ Heatmap height | ⚠️ | ✅ | Height responsivo |
| `ranking` | ⚠️ Charts height | ⚠️ | ✅ | Height responsivo |
| `calculadora` | ✅ Forms stack | ✅ | ✅ | - |
| `revisao` | ⚠️ Cards 2→1 col | ✅ | ✅ | Verificar CSS |
| `lojas` | ✅ Form stack | ✅ | ✅ | - |
| `ingredientes` | ✅ Tabs nativas | ✅ | ✅ | - |
| `alertas` | ✅ Pagination nativa | ✅ | ✅ | - |
| `scrapers` | ✅ Tables scroll | ✅ | ✅ | - |
| `scraper_health` | ✅ KPIs stack | ✅ | ✅ | Chart height |
| `relatorios` | ✅ Form stack | ✅ | ✅ | Iframe height |
| `flyers` | ✅ Grid 1 col | ✅ Grid 2 cols | ✅ Auto-fill | - |
| `config` | ✅ Forms stack | ✅ | ✅ | - |
| `diagnostico` | ✅ Tabs | ✅ | ✅ | - |
| `ci_telemetry` | ✅ KPIs stack | ✅ | ✅ | - |
| `capacity_planning` | ✅ KPIs stack | ✅ | ✅ | - |

---

## Análise de Performance

### Queries por Página (Cold Cache)

| Página | Queries | Tempo Estimado | Otimização |
|--------|---------|----------------|------------|
| `visao_geral` | 5 sequenciais | ~2.5s | **Unificar em `_single_pass_prices()`** (já existe!) |
| `precos` | 1 (server-side) | ~0.5s | OK |
| `historico` | 1 | ~0.8s | OK |
| `promocoes` | 1 (500 limit) | ~0.6s | OK |
| `insights` | 1 + loop Python | ~1.5s | **Mover outliers para DB** |
| `fontes` | 1 + 1 | ~0.8s | OK |
| `ranking` | 3 (por tab) | ~1.2s | `st.fragment` por tab |
| `calculadora` | N (por ingrediente) | ~N*0.3s | Batch `get_cheapest_prices_cached` |
| `revisao` | 1 (500 limit) | ~0.7s | OK |
| `lojas` | 2 | ~0.5s | OK |
| `lojas_pendentes` | 2 | ~0.5s | OK |
| `ingredientes` | 1-3 | ~0.5s | OK |
| `alertas` | 1-3 | ~0.5s | OK |
| `scrapers` | 2-3 | ~0.8s | OK |
| `scraper_health` | 3-4 | ~1.0s | `st.fragment` por tab |
| `relatorios` | 1 | ~0.6s | OK |
| `flyers` | 1 | ~0.5s | OK |
| `config` | 3-4 | ~0.6s | OK |
| `diagnostico` | 4-6 | ~1.5s | Benchmarks propositalmente slow |
| `ci_telemetry` | 0 (file read) | ~0.1s | OK |
| `capacity_planning` | 3 RPCs | ~1.0s | OK |

### Cache Strategy
- `@st.cache_data(ttl=300)` em todas queries `dashboard_queries.py`
- `clear_all_caches()` invalida `dashboard_cache` + `dashboard_data_cache`
- **Problema**: `visao_geral` não usa `_single_pass_prices` — faz 5 calls ao cached helper

---

## Consistência Visual & Design System

### Design Tokens (CSS Variables)
```css
:root {
  --cd-orange: #F59E42;      /* Primary actions */
  --cd-pink: #E8739A;        /* Secondary/accents */
  --cd-blue: #3B7DD8;        /* Info */
  --cd-success: #10B981;     /* Success */
  --cd-warning: #F59E0B;     /* Warning */
  --cd-danger: #EF4444;      /* Error/Destructive */
  --cd-bg: #FFF9F5;          /* App background */
  --cd-bg-card: #FFFFFF;     /* Card background */
  --cd-text: #3D2C1E;        /* Primary text */
  --cd-text-secondary: #8B7355;
  --cd-border: #F0E6DB;
  --cd-radius: 14px;
  --cd-font: 'Nunito', sans-serif;
}
```

### Inconsistências Detectadas

| Elemento | Padrão Esperado | Variações Encontradas |
|----------|-----------------|----------------------|
| KPI Cards | `kpi_card()` component | `st.metric` direto (8 páginas), `kpi_card` (2 páginas) |
| Buttons Primary | `type="primary"` + gradient CSS | Alguns sem gradient, alguns `st.button` sem type |
| Tables | `st.dataframe(column_config=..., hide_index=True, use_container_width=True)` | Alguns sem `column_config`, alguns com `hide_index=False` |
| Dialogs | `st.dialog` + 2 colunas (Cancelar/Confirmar) | `flyers.py` usa, `revisao.py` usa inline buttons |
| Forms | `st.form` + `form_submit_button` | `calculadora.py` usa, `ingredientes.py` usa, `config.py` batch form |
| Tabs | `st.tabs` | `ranking.py`, `lojas.py`, `ingredientes.py`, `alertas.py`, `scrapers.py`, `relatorios.py`, `config.py`, `diagnostico.py` |
| Empty States | `st.info("...")` / `st.success("...")` | Consistente |
| Loading | `with st.spinner("..."):` | Consistente |
| Toasts | **Não usado** | `st.success`/`st.error`/`st.warning`/`st.info` persistem no rerun |

### Recomendação: Adotar `st.toast` (Streamlit 1.31+)
```python
# Substituir:
st.success("Salvo!")
st.rerun()

# Por:
st.toast("Salvo com sucesso!", icon="✅")
st.rerun()
```

---

## Plano de Testes Completo

### Fase 1: Testes Locais Automatizados (Pré-Push)

```bash
# 1. Lint + Typecheck + Unit + Schema (obrigatório)
ruff check . && python -m mypy . && python -m pytest tests/unit/ tests/schema/ -q

# 2. Testes de componente Streamlit (headless)
python -m pytest tests/e2e/test_e2e_smoke_basic.py -v

# 3. Testes de acessibilidade (axe-core)
python -m pytest tests/a11y/ -v  # Criar se não existir

# 4. Visual regression baselines (local)
UPDATE_BASELINES=1 python -m pytest tests/e2e/test_e2e_dashboard.py::test_visual_regression -v
```

### Fase 2: Testes Locais com DB Real (Staging)

```bash
# 1. Subir Stack local (se houver docker-compose) ou usar Supabase staging
export SUPABASE_URL=<staging_url>
export SUPABASE_SERVICE_ROLE_KEY=<staging_key>
export ADMIN_PASSWORD=<senha>

# 2. Rodar Streamlit local
streamlit run admin/app.py --server.port 8501 &

# 3. E2E completo local (Playwright)
STREAMLIT_URL=http://localhost:8501 python -m pytest tests/e2e/test_e2e_dashboard.py -v

# 4. Testes de integração Supabase
python -m pytest tests/integration/ -v

# 5. Testes de calibração scoring
python -m pytest tests/calibration/ -v
```

### Fase 3: Testes na Cloud (Streamlit Cloud)

```bash
# 1. Deploy para staging branch
git push origin staging  # CI roda e2e.yml contra cloud

# 2. Ou disparar workflow manual
gh workflow run e2e.yml -f base_url=https://custodoce-staging.streamlit.app

# 3. Testes manuais críticos (checklist):
#    □ Login + 2FA
#    □ Navegação todos 21 menus (sidebar + st.navigation)
#    □ Filtros e deep-links (query_params persistem)
#    □ Mobile: Chrome DevTools device toolbar (iPhone 14, iPad, Desktop)
#    □ Acessibilidade: Tab navigation, screen reader (NVDA/VoiceOver)
#    □ Performance: Lighthouse CI (LCP < 2.5s, CLS < 0.1)
#    □ Visual: Comparar screenshots com baselines aprovados
```

### Fase 4: Testes de Carga & Stress

```bash
# 1. Locust test (simular 50 users concurrentes)
locust -f tests/load/locustfile.py --host=https://custodoce.streamlit.app

# 2. Cache stress: clear_all_caches + 100 requests simultâneos
# 3. DB connection pool: verificar limites Supabase
```

---

## Matriz de Testes Funcionalidade por Funcionalidade

| Funcionalidade | Página | Unit | Integration | E2E Local | E2E Cloud | A11y | Visual | Performance |
|----------------|--------|------|-------------|-----------|-----------|------|--------|-------------|
| Login + 2FA | `login_page.py` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Navegação sidebar | `layout.py` | ✅ | - | ✅ | ✅ | ✅ | ✅ | - |
| KPIs Visão Geral | `visao_geral.py` | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ | 🔴 |
| Filtros Preços | `precos.py` | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| Histórico Gráficos | `historico.py` | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| Promoções | `promocoes.py` | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| Heatmap Insights | `insights.py` | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 🔴 |
| Outliers | `insights.py` | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 🔴 |
| Fontes Ranking | `fontes.py` | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| Ranking 3 tabs | `ranking.py` | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| Calculadora 3 modos | `calculadora.py` | ❌ | ✅ | ✅ | ✅ | 🔴 | ✅ | ⚠️ |
| Revisão Aprovar/Rejeitar | `revisao.py` | ❌ | ✅ | ✅ | ✅ | 🔴 | ✅ | ✅ |
| Lojas CRUD | `lojas.py` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Lojas Pendentes | `lojas_pendentes.py` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Ingredientes CRUD | `ingredientes.py` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Alertas Pagination | `alertas.py` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Scrapers Logs | `scrapers.py` | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| Scraper Health | `scraper_health.py` | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| Relatórios Builder | `relatorios.py` | ❌ | ✅ | ✅ | ✅ | 🔴 | ✅ | ✅ |
| Flyers Grid + Delete | `flyers.py` | ✅ | ✅ | ✅ | ✅ | 🔴 | ✅ | ✅ |
| Config Batch Forms | `config.py` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Diagnóstico | `diagnostico.py` | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CI Telemetria | `ci_telemetry.py` | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| Capacity Planning | `capacity_planning.py` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**Legenda**: ✅ = Coberto | ⚠️ = Parcial | 🔴 = Gap Crítico | ❌ = Não testado

---

## Ações Prioritárias (Backlog Ordenado)

### 🔴 Crítico (Fazer Agora - Sprint 17/18)

| # | Ação | Arquivo(s) | Esforço | Impacto |
|---|------|------------|---------|---------|
| 1 | Corrigir `label_visibility="collapsed"` em `calculadora.py:39` | `calculadora.py` | 15 min | A11y compliance |
| 2 | Implementar "Adicionar como Alias" em `revisao.py` | `revisao.py`, `services/config_db.py` | 30 min | Funcionalidade core |
| 3 | Implementar "Criar Nova Loja" em `lojas_pendentes.py` | `lojas_pendentes.py`, `services/config_db.py` | 30 min | Funcionalidade core |
| 4 | Mover outlier detection para DB (RPC) | `insights.py`, `supabase/migration.sql` | 2h | Performance + UX |
| 5 | Unificar `visao_geral` para usar `_single_pass_prices()` | `visao_geral.py`, `dashboard_queries.py` | 30 min | Performance |
| 6 | Adicionar `caption` em todas `st.image` | `revisao.py`, `flyers.py`, `lojas_pendentes.py` | 1h | A11y |
| 7 | Adicionar `title` no iframe `relatorios.py:141` | `relatorios.py` | 5 min | A11y |
| 8 | Remover duplicação `lojas_pendentes` ↔ `lojas.py` Tab 2 | `lojas.py`, `navigation_config.py` | 30 min | Manutenibilidade |
| 9 | Remover duplicação Destinatários `alertas.py` ↔ `config.py` | `config.py`, `navigation_config.py` | 15 min | Manutenibilidade |
| 10 | Remover `lojas_registro` do `MENU_GROUPS` | `navigation_config.py` | 5 min | UX |

### 🟡 Alto (Próximas 2 Sprints)

| # | Ação | Arquivo(s) | Esforço |
|---|------|------------|---------|
| 11 | Adicionar `st.toast` substituindo `st.success/error` persistentes | Todas pages | 2h |
| 12 | Gráficos Plotly responsivos (`height=None`, `use_container_width=True`) | `visao_geral`, `historico`, `insights`, `ranking`, `scraper_health` | 1h |
| 13 | Descrições textuais para todos gráficos (screen readers) | Pages com Plotly | 2h |
| 14 | `st.fragment` para seções independentes (KPIs, tabs, grids) | `visao_geral`, `ranking`, `scraper_health`, `calculadora` | 2h |
| 15 | Paginação `st.pagination` em tabelas >50 rows | `precos`, `alertas`, `flyers`, `scrapers`, `revisao` | 1h |
| 16 | Validação live JSON em `lojas.py` selectors | `lojas.py` | 30 min |
| 17 | Sanitizar keys `add_alias_{s}` → `add_alias_{hash(s)}` | `ingredientes.py` | 15 min |
| 18 | Mover queries Supabase diretas para `dashboard_queries.py` | `calculadora.py`, `diagnostico.py`, `lojas.py` | 1h |
| 19 | Tabela `email_logs` real para SMTP quota | `capacity_planning.py`, migration | 1h |
| 20 | Documentar geração `minutes_report.json` no CI | `ci_telemetry.py`, `.github/workflows/` | 30 min |

### 🟢 Médio (Backlog Contínuo)

| # | Ação | Arquivo(s) | Esforço |
|---|------|------------|---------|
| 21 | Padronizar KPI cards: usar `kpi_card()` em vez de `st.metric` | 8 pages | 1h |
| 22 | Export CSV buttons em todas tabelas | Pages com `st.dataframe` | 2h |
| 23 | Keyboard shortcuts hints (Ctrl+Enter, etc.) | Forms principais | 30 min |
| 24 | Loading skeletons (`st.empty` + placeholder) | Pages com queries lentas | 1h |
| 25 | Error boundaries por seção (try/catch granular) | `visao_geral`, `ranking` | 1h |
| 26 | Theme switcher (light/dark) | `.streamlit/config.toml` + CSS | 2h |
| 27 | Internacionalização (i18n) PT-BR/EN | Todas strings | 4h |
| 28 | Testes de carga automatizados no CI | `tests/load/` | 2h |
| 29 | Visual regression no CI (baselines aprovados) | `tests/e2e/` | 1h |
| 30 | Dashboard de métricas de UX (rage clicks, tempo por página) | Novo módulo | 4h |

---

## Checklist de Validação Final (Definition of Done)

### Por Página
- [ ] Carrega < 3s (cold cache)
- [ ] Mobile: 320px-428px sem scroll horizontal quebrado
- [ ] Tablet: 768px-1024px layout adequado
- [ ] Desktop: 1440px+ aproveita espaço
- [ ] A11y: Tab navigation completo, skip link funciona, focus visible
- [ ] A11y: Screen reader anuncia conteúdo principal
- [ ] A11y: Contraste ≥ 4.5:1 em todos textos
- [ ] A11y: Imagens têm alt text/caption
- [ ] A11y: Formulários têm labels visíveis + help text
- [ ] A11y: Erros são descritivos (não "Erro")
- [ ] Deep-links funcionam (query_params persistem)
- [ ] Loading states em queries >500ms
- [ ] Empty states amigáveis
- [ ] Toast notifications para ações (não alertas persistentes)
- [ ] Visual regression passa (baseline aprovado)

### Sistema
- [ ] CI `lint` + `typecheck` + `unit` + `schema` passa
- [ ] CI `e2e` passa (cloud + local)
- [ ] CI `visual-regression` passa
- [ ] CI `a11y` passa (axe-core)
- [ ] CI `load` passa (50 users, p95 < 3s)
- [ ] Supabase staging: dados íntegros (D1-D10)
- [ ] Free tier limits: disco < 70%, Actions < 80%, SMTP < 80%
- [ ] Documentação atualizada (`AGENTS.md`, `docs/skills.md`, `CHANGELOG.md`)

---

## Comandos de Referência Rápida

```bash
# Desenvolvimento local
streamlit run admin/app.py --server.port 8501

# Testes rápidos (pre-push)
ruff check . && python -m mypy . && python -m pytest tests/unit/ tests/schema/ -q

# E2E local (requer Streamlit rodando em :8501)
STREAMLIT_URL=http://localhost:8501 python -m pytest tests/e2e/test_e2e_dashboard.py -v

# Visual regression - criar baselines
UPDATE_BASELINES=1 python -m pytest tests/e2e/test_e2e_dashboard.py::test_visual_regression -v

# Visual regression - comparar
python -m pytest tests/e2e/test_e2e_dashboard.py::test_visual_regression -v

# A11y audit (requer axe-selenium)
python -m pytest tests/a11y/ -v

# Lighthouse CI (performance)
npx lighthouse http://localhost:8501 --output=json --output-path=./lighthouse.json

# Deploy staging + testes cloud
git push origin staging  # CI roda e2e.yml

# Ver logs CI
gh run view --log

# Capacidade atual
python -c "from dashboard.pages.capacity_planning import render_capacity_planning; render_capacity_planning()"
```

---

## Referências

- [Streamlit 1.58 Release Notes](https://docs.streamlit.io/develop/release-notes)
- [WCAG 2.1 Guidelines](https://www.w3.org/TR/WCAG21/)
- [CustoDoce AGENTS.md](../AGENTS.md)
- [CustoDoce REGRAS.md](../REGRAS.md)
- [CustoDoce LESSONS.md](../LESSONS.md)
- [Dashboard Navigation Config](../dashboard/navigation_config.py)
- [Streamlit Components Skill](../.opencode/skills/streamlit-components/SKILL.md)
- [Streamlit Responsive Skill](../.opencode/skills/streamlit-responsive/SKILL.md)
- [Streamlit Theming Skill](../.opencode/skills/streamlit-theming/SKILL.md)
- [Accessibility Skill](../.opencode/skills/accessibility/SKILL.md)

---

*Documento gerado em 2026-08-08 como parte da Sprint 17 - Análise UX Completa. Próxima revisão: Sprint 18.*