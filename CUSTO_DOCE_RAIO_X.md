# 🍬 CUSTO DOCE RAIO-X
## Análise Completa do Projeto

## 📊 1. VEREDITO EXECUTIVO

| Indicador | Valor |
| :--- | :--- |
| **Nome** | CustoDoce — Busca e comparação de preços de ingredientes para confeitaria |
| **Público** | Confeiteiros profissionais/amadores — Baixada Santista + SP Capital |
| **Stack** | Python 3.12 (runtime.txt + CI + mypy) + Streamlit + Supabase (PostgreSQL) + GitHub Actions |
| **Nota** | **8.0/10** — Arquitetura sólida, pipeline de matching sofisticado. Corrigir segurança da service_role e atualizar testes. |
| **Risco** | 🟡 MÉDIO |
| **Recomendação** | ✅ MANTER E CORRIGIR |

### 🔴 Gargalos + Riscos Prioritários

| # | Problema | Onde | Impacto |
| :--- | :--- | :--- | :--- |
| 1 | SERVICE_ROLE_KEY exposta no dashboard (`get_service_client()`) | `price_repository.py:8` chamado pelo Streamlit | 🔴 CRÍTICO — vazamento = acesso total ao banco |
| 2 | RPC `exec_sql_query` aceita SQL arbitrário sem sanitização | `consolidated_migration.sql:959` | 🔴 CRÍTICO — se service_role vazar, invasor executa qualquer SQL |
| 3 | Testes desatualizados — doc diz 16 unit, real são 417 | `CUSTO_DOCE_RAIO_X.md` | 🟠 ALTO — documentação enganosa |
| 4 | Busca de preços no dashboard sem cache (toda consulta vai ao Supabase) | `dashboard/pages/`, `price_repository.py` | 🟡 MÉDIO — latência em toda requisição |
| 5 | Normalizer sem fallback: se `parse_unit()` falha, produto é perdido | `normalizer.py:91` | 🟡 MÉDIO — produtos sem unidade reconhecível descartados |

### 🛠️ Ações Imediatas (3 dias)

1. Criar role `dashboard_user` no Supabase (SELECT + INSERT review_queue + EXECUTE RPCs específicas) — **nunca usar service_role no dashboard**
2. Remover ou sanitizar RPC `exec_sql_query` — substituir por RPCs nomeadas
3. Atualizar suíte `pytest` para rodar com o código atual

### ⚙️ Feature Flags (config/features.yaml + config.py)

Sistema de configuração em 2 níveis:
- **Global**: `get("features.ai.llm_classifier", True)` em `llm_classifier.py:72`
- **Per-ingrediente**: `get_feature("features.scrapers.vtex", ingredient="Leite Condensado")` verifica `features.overrides[ingredient].features.scrapers.vtex` primeiro, depois cai para global (`config.py:33-46`)
- Cache LRU do YAML com `reload()` para recarregar sem reiniciar

---

## 🧰 2. TECNOLOGIAS

### Stack Principal

| Camada | Tecnologia | Versão |
| :--- | :--- | :--- |
| Frontend | Streamlit | ≥1.28 (`requirements.txt`) |
| Backend | Python | 3.12 (unificado) |
| Banco | Supabase (PostgreSQL 15) | N/A |
| ML/AI | Sentence-Transformers + ONNX | ≥2.7 |
| LLM | Groq (llama-3.3-70b) → OpenRouter (Mixtral) → HF (Mistral) | — |
| Anomalias | scikit-learn Isolation Forest | ≥1.5 |
| Orquestração | GitHub Actions (7 workflows) | — |

### Bibliotecas-Chave

| Biblioteca | Versão | Função | Referência |
| :--- | :--- | :--- | :--- |
| `supabase` | ≥2.0 | Cliente REST + RPC | `services/supabase_client.py` |
| `httpx` | ≥0.27 | HTTP para scrapers | `scrapers/base_*.py` |
| `pdfplumber` | ≥0.11 | Extração de PDFs | `base_flyer.py:112` |
| `pytesseract` | ≥0.3 | OCR fallback | `scrapers/ocr.py` |
| `rapidfuzz` | ≥3.0 | Fuzzy matching (token_set_ratio) | `matcher.py:55` |
| `sentence-transformers` | ≥2.7 | Embeddings semânticos | `semantic_matcher.py` |
| `optimum` + `onnxruntime` | — | Inferência ONNX acelerada | `semantic_matcher.py:38` |
| `groq` | ≥0.9 | LLM classificação primária | `llm_strategies.py:113` |
| `scikit-learn` | ≥1.5 | Isolation Forest | `price_intelligence.py:107` |
| `python-telegram-bot` | ≥21 | Bot Telegram | `handlers.py` |
| `selectolax` | ≥0.3 | CSS selectors (rápido) | `carrefour_scraper.py` |
| `structlog` | ≥24.0 | Logging estruturado | `services/logger.py` |
| `opentelemetry-api` | ≥1.24 | Tracing distribuído | `services/otel.py` |
| `plotly` | ≥5.18 | Gráficos | `dashboard/components/ui.py` |

### Integrações Externas

| Serviço | Função | Onde |
| :--- | :--- | :--- |
| Supabase | DB + API REST + RLS + RPC | `services/supabase_client.py` |
| Groq / OpenRouter / HuggingFace | LLM fallback chain (3 providers) | `parsers/llm_strategies.py` |
| Telegram Bot API | Bot de consultas (6 comandos) | `telegram_bot/handlers.py` |
| Gmail SMTP | Relatórios diários por e-mail | `services/email_service.py` |
| GitHub Actions | CI/CD + cron scrapers + backup + e2e | `.github/workflows/*.yml` |

---

## 🏗️ 3. ARQUITETURA

### 3.1. Fluxo (texto)

```
[GitHub Actions Cron]
  │ (seg/qua/qui/sex 12h UTC + sáb + 1º do mês)
  ▼
[main.py] ───────────────────────────────────────────────────────┐
  │ sync_store_fields() → yaml ↔ DB                                │
  │ collect_tier1_pdfs()    → FlyerScraper → pdfplumber → OCR      │
  │ collect_extra_flyers()  → ExtraFlyerScraper (HTTP + JS data)   │
  │ collect_pao_flyers()    → PaoFlyerScraper (herda Extra)        │
  │ collect_tier1_api()     → TendaApi / RoldaoApi / MaxApi        │
  │ process_ocr_queue()     → OCR fallback em lote                 │
  │ collect_tier2_vtex()    → VtexScraper (API VTEX)               │
  │ collect_tier3_websites()→ WebsiteScraper (CSS selectors)       │
  │ collect_carrefour()     → CarrefourScraper                     │
  │ collect_tier2_js()      → PlaywrightPriceScraper (JS)          │
  │ collect_aggregators()   → TiendeoScraper (async)               │
  │                                                               │
  ├── [collector.py: process_price_match()]                       │
  │   ├── match_exact()/fuzzy() → se ≥80%: upsert imediato        │
  │   ├── se 55-79%: semantic_matcher.blend (0.6 fuzz+0.4 emb)    │
  │   ├── se 65-80%: llm_classifier (Groq→OR→HF→fallback)        │
  │   └── se <55%: review_queue com match_type/reason/top3        │
  │                                                               │
  ├── [price_repository.py: upsert_price()]                       │
  │   Tenta RPC upsert_price_rpc() → fallback INSERT/UPDATE       │
  │   ↓ Supabase: trigger → price_history + MV v_latest_prices    │
  │                                                               │
  ├── [price_intelligence.py: enrich_prices()]                    │
  │   Z-score ±2 → Isolation Forest → tags                        │
  │                                                               │
  ├── Snapshot → data/prices_latest.json                          │
  ├── Email → send_daily_report()                                 │
  ├── Cleanup → 5 funções TTL (prices 90d, logs 30d, etc.)       │
  └── Alertas → alert_service.process_proactive_alerts()          │
                                                                    │
─── CONSULTA ──────────────────────────────────────────────────────┘
Telegram: /preco <ing> → search_prices() → top 10 🥇🥈🥉
Dashboard: Streamlit → 17 páginas → Supabase (anon/SELECT)
```

### 3.2. Estrutura de Pastas

```
CustoDoce/
├── .github/workflows/   7 workflows (ci, scrape, backup, restore-test, e2e, deploy-staging, on-demand)
├── admin/               Entrypoint Streamlit (app.py:126) + 17 tabs/ (visao_geral, precos, etc.)
├── config/              4 arquivos: ingredients.yaml (23 itens), stores.yaml (51 lojas/4 tiers), features.yaml, schema_prices.json
├── dashboard/           components/ (ui.py CSS, layout.py sidebar), login_page.py (auth+TOTP), pages/ (17 módulos)
├── data/                Caches: embeddings .npy, ONNX model, llm_cache.db (SQLite), prices_latest.json
├── docs/                ADR (5), API docs, architecture, changelog, deployment, security, rollback
├── parsers/             8 arquivos: normalizer, matcher, brand_extractor, unit_extractor, semantic_matcher, llm_cache, llm_strategies, llm_classifier
├── scrapers/            18 arquivos: base_flyer, base_web, flyer_scraper, flyer_parser, extra_flyer, pao_flyer, vtex, website, carrefour, tenda_api, roldao_api, roldao_flyer_scraper, max_api, aggregator, playwright_pool, playwright_scraper, playwright_price_scraper, ocr
├── scripts/             Deploy, validação, seed, sync, auditoria (39 scripts)
├── services/            23 arquivos: price_repository, price_service (facade), price_analytics, price_intelligence, collector, review_queue_service, config_db, config, alert_service, email_service, telegram_service, auth, rate_limiter, recipe_service, flyer_service, import_service, maintenance_service, dashboard_queries, logger, otel, types, supabase_client
├── supabase/            consolidated_migration.sql (861 linhas, 20 fases) + migrations/001_config_tables.sql + 3 migrações avulsas
├── telegram_bot/        handlers.py (154 linhas, 6 comandos)
├── tests/               unit/ (417), schema/ (94 parametrized), integration/ (100), e2e/ (0 collected — 3 arquivos, requer Playwright), real/ (6)
├── main.py              Orquestrador principal (154 linhas)
└── pyproject.toml       Ruff (120 chars), mypy (3.12), pytest config
```

### 3.3. Padrões de Projeto (9 identificados)

| Padrão | Onde | Descrição |
| :--- | :--- | :--- |
| **Service Layer** | `services/` | Toda lógica de negócio encapsulada em serviços |
| **Repository** | `price_repository.py` | Acesso a dados isolado com fallback RPC → table direta |
| **ABC + Template Method** | `base_flyer.py`, `base_web_scraper.py` | Contrato + esqueleto: `run()` = download→extract→parse |
| **Strategy** | `llm_strategies.py` | 3 providers (Groq, OpenRouter, HF) mesmo contrato |
| **Circuit Breaker** | `llm_strategies.py` | 3 falhas consecutivas → cooldown 10 min por provider |
| **Singleton** | `supabase_client.py`, `playwright_pool.py` | Conexão única ao Supabase + pool único de browsers |
| **Facade** | `price_service.py` | Fachada unificando price_repository + review_queue + analytics |
| **Pipeline** | Matching (matcher → semantic → llm → review) | 6 estágios encadeados com thresholds |
| **Cache-Aside** | `llm_cache.py` (SQLite SHA-256, TTL 30d), `semantic_matcher.py` (disco .npy) | Reduz chamadas externas redundantes |

---

## 🗄️ 4. MODELAGEM DO BANCO (13 tabelas)

### Relacionamentos

```
prices (N) ──→ ingredients (1) via ingredient_id TEXT
prices (N) ──→ stores (1) via store_id TEXT
price_history (N) ──→ prices (N) via price_id FK (ON DELETE SET NULL)
recipes (1) ──→ recipe_items (N) via recipe_id FK (ON DELETE CASCADE)
scrape_frequencies (N) ──→ stores (1) via store_id FK (ON DELETE CASCADE)
flyers (N) ──→ stores (N) via store_name TEXT
review_queue independente (status: pending/approved/rejected)
```

### `prices` — Tabela principal

`id UUID PK` | `ingredient_id TEXT NOT NULL` | `store_id TEXT NOT NULL` | `source TEXT NOT NULL` | `store_name TEXT` | `raw_product TEXT NOT NULL` | `raw_price DECIMAL(10,2) NOT NULL` | `raw_unit TEXT` | `collected_at TIMESTAMPTZ` | `valid_from DATE` | `valid_until DATE DEFAULT NOW()+7d` | `validity_raw TEXT` | `collected_weekday TEXT` | `is_promotion BOOLEAN` | `tier INTEGER` | `confidence DECIMAL(4,3)` | `normalized JSONB` (qty/unit_kg/total_kg/price_per_kg/price_per_un) | `city TEXT` | `logistics TEXT` | `brand TEXT` | `price_per_kg NUMERIC GENERATED` | `created_at TIMESTAMPTZ`

**UNIQUE**: `(ingredient_id, store_id, collected_at)` | **20 índices**

### `price_history` — Histórico via trigger

`id UUID PK` | `price_id UUID FK→prices` | `ingredient_id TEXT NOT NULL` | `store_id TEXT NOT NULL` | `store_name TEXT` | `raw_product TEXT` | `raw_price DECIMAL(10,2)` | `raw_unit TEXT` | `normalized JSONB` | `valid_from/valid_until DATE` | `validity_raw TEXT` | `collected_weekday TEXT` | `is_promotion BOOLEAN` | `collected_at TIMESTAMPTZ` | `brand TEXT` | `price_per_kg NUMERIC GENERATED`

**UNIQUE**: `(ingredient_id, store_id, collected_at)` | **8 índices**

### `review_queue` — Fila de revisão manual

`id UUID PK` | `raw_product TEXT NOT NULL` | `raw_price DECIMAL(10,2)` | `raw_unit TEXT` | `store_name TEXT` | `source TEXT` | `confidence DECIMAL(4,3)` | `suggestions JSONB` | `validity_raw TEXT` | `status TEXT` (pending/approved/rejected) | `resolved_ingredient TEXT` | `brand TEXT` | `image_url TEXT` | `source_url TEXT` | `match_reason TEXT` | `match_type TEXT` | `top3 JSONB` | `collected_at TIMESTAMPTZ` | `reviewed_at TIMESTAMPTZ`

**UNIQUE**: `(store_name, raw_product)` | **3 índices**

### `ingredients` — 23 canônicos

`id UUID PK` | `canonical_name TEXT UNIQUE NOT NULL` | `category TEXT` | `aliases TEXT[]` | `brands TEXT[]` | `search_terms TEXT[]` | `unit_target TEXT` (kg) | `active BOOLEAN` | `created_at/updated_at TIMESTAMPTZ` (trigger updated_at)

### `stores` — 51 lojas

`id TEXT PK` | `name TEXT NOT NULL` | `tier INTEGER` (1-4) | `type TEXT` | `scraper TEXT` | `url_pattern/base_url/search_url/api_endpoint TEXT` | `selectors JSONB` | `logistics/city/zone/coverage TEXT` | `is_active BOOLEAN` | `priority INTEGER` | `publish_day/visit_frequency/contact TEXT` | `config JSONB` | `created_at/updated_at TIMESTAMPTZ`

### `flyers` — Metadados

`id UUID PK` | `store_name TEXT NOT NULL` | `region TEXT NOT NULL` | `city TEXT` | `flyer_title TEXT` | `flyer_date_start/end DATE` | `image_url TEXT NOT NULL` | `image_hash TEXT` | `image_type TEXT` | `image_width/height INT` | `ocr_status TEXT` (pending/done/failed) | `ocr_text TEXT` | `ocr_confidence DECIMAL(4,3)` | `products_extracted INT` | `source TEXT` (tiendeo) | `valid_from/until DATE` | `collected_at/processed_at TIMESTAMPTZ`

**UNIQUE**: `(store_name, region, image_hash)`

### `scraping_logs`

`id UUID PK` | `store_name TEXT NOT NULL` | `status TEXT` (started/completed/failed) | `started_at/finished_at TIMESTAMPTZ` | `items_found/matched INT` | `errors JSONB` | `duration_seconds INT`

### `recipes` + `recipe_items`

| Tabela | Colunas |
| :--- | :--- |
| recipes | `id UUID PK`, `name TEXT NOT NULL`, `yield_qty INT` (40), `overhead_pct DECIMAL(5,1)` (15%), `profit_pct DECIMAL(7,1)` (300%), `created_at` |
| recipe_items | `id UUID PK`, `recipe_id UUID FK→recipes CASCADE`, `ingredient_id TEXT`, `quantity_g DECIMAL(10,1)`, `selected_store TEXT`, `price_per_kg DECIMAL(10,2)` |

### `scrape_frequencies` (FK→stores)

`id UUID PK` | `store_id TEXT FK CASCADE` | `tier INT` | `frequency_minutes INT` (1440) | `max_retries INT` (2) | `timeout_seconds INT` (30) | `rate_limit_per_minute INT` (10) | `enabled BOOLEAN`

### `schedules`

`id UUID PK` | `name TEXT UNIQUE` | `cron_expression TEXT` | `timezone TEXT` (America/Sao_Paulo) | `payload JSONB` | `enabled BOOLEAN` | `last_run/next_run TIMESTAMPTZ`

### `alert_recipients`

`id UUID PK` | `channel TEXT CHECK` (email/telegram/whatsapp) | `target TEXT NOT NULL` | `name TEXT` | `active BOOLEAN`

### `alert_rules`

`id UUID PK` | `name TEXT NOT NULL` | `channel TEXT CHECK` | `trigger TEXT CHECK` (price_drop/new_low_price/daily_report/scrape_failure/review_queue_threshold) | `condition JSONB` | `frequency_minutes INT` (1440) | `recipients UUID[]` | `template TEXT` | `enabled BOOLEAN`

### `feature_flags` + `llm_match_cache`

| Tabela | Colunas |
| :--- | :--- |
| feature_flags | `key TEXT PK`, `enabled BOOLEAN`, `description TEXT`, `updated_at` |
| llm_match_cache | `id UUID PK`, `product_hash TEXT UNIQUE` (SHA-256), `product_name TEXT`, `ingredient_id TEXT`, `match_result JSONB`, `confidence DECIMAL(4,3)`, `provider TEXT`, `created_at`, `expires_at` (TTL 30d) |

### Materialized View: `v_latest_prices`

```sql
SELECT DISTINCT ON (ingredient_id, store_id) ... FROM prices
WHERE valid_from ≤ TODAY AND valid_until ≥ TODAY
AND price_per_kg IS NOT NULL AND > 0
ORDER BY ingredient_id, store_id, collected_at DESC
```
Índices: UNIQUE(ingredient_id, store_id), ingredient, price_per_kg

### RLS Policies

- **Todas as tabelas**: RLS habilitado
- **Config (ingredients, stores, etc.)**: `service_role ALL`, `anon SELECT`
- **Prices/History**: `anon SELECT`, `service_role INSERT/UPDATE`
- **Config tables (Phase 3)**: `service_role ALL`, `anon SELECT`
- **Recipes/RecipeItems**: `service_role ALL`, `anon SELECT`
- **RPCs**: `exec_sql`, `exec_sql_query`, `upsert_price_rpc` — SECURITY DEFINER (bypass RLS)

### Índices Sugeridos

| Sugestão | Para quê |
| :--- | :--- |
| `idx_prices_valid_range` ON (valid_from, valid_until) | Queries de validade (usadas em todo dashboard) |
| `idx_prices_ingredient_valid` ON (ingredient_id, valid_until, valid_from) | Consulta composta mais comum |
| `idx_alert_rules_trigger_enabled` ON (trigger, enabled) | Alert service |

---

## 📱 5. DASHBOARD (17 telas)

### Navegação

```
Login (login_page.py: auth + TOTP + rate limiter + setup first user)
  └─ Sidebar (layout.py: PAGES dict, logo, logout, clear cache)
       ├─ 📊 Visão Geral — KPIs (total preços, ingredientes, lojas, média R$/kg), promoções, cobertura, rankings
       ├─ 💰 Preços — Filtros (ingrediente/loja/tier), tabela com R$/kg, R$/un, promoção, marca
       ├─ 📈 Histórico — Gráfico (linha/área/barras/dispersão), estatísticas por loja
       ├─ 📄 Flyers — Grid thumbnails, detalhes, produtos extraídos, excluir
       ├─ 🔍 Revisão — Aprovar/rejeitar (filtro confiança + match_type + brand override + top3 candidatos)
       ├─ 🏪 Fontes — Cobertura por ingrediente, promoções ativas, ranking de fontes
       ├─ 🏆 Ranking — Vencedores 90d, heatmap cruzado, tendências
       ├─ 💡 Insights — Heatmap cobertura, outliers (z>2), top 10 ofertas
       ├─ 🏬 Lojas — Lista, adicionar/editar formulário + editor YAML stores.yaml
       ├─ 🥘 Ingredientes — Lista/editar, testar normalizer, testar matcher, sugerir aliases
       ├─ 🧮 Calculadora — Simples (custo rápido) / Completo (monofonte/multifonte), salvar receita
       ├─ 🤖 Scrapers — Status & Logs, Agendamentos (cron), Health Check manual
       ├─ 📬 Relatórios — Builder HTML + Telegram, testar SMTP, testar Telegram
       ├─ ⚙️ Config — Secrets .env, Feature Flags, Alert Rules, Destinatários, Recarregar
       ├─ 🩺 Diagnóstico — Performance, Conectividade, Integridade, Capacity Planning (free tier)
       └─ 🔔 Alertas — Regras ativas, criar regra, gerenciar destinatários
```

---

## ⚙️ 6. FUNÇÕES CORE

### `services/price_repository.py`

`upsert_price(entry)` → RPC upsert_price_rpc (19 params) → fallback INSERT/UPDATE direto na tabela | `search_prices(ingredient, sort_by, order, limit, tier, logistics, city, valid_only)` → query com filtros | `get_latest_prices(valid_only, limit=2000)` → v_latest_prices com filtro validade | `get_price_history(ingredient, days=30, valid_only)` → price_history filtrado | `_detect_promotion(raw_product, raw_unit)` → regex "promo|oferta|desconto|N% off" | `_weekday_pt(dt)` → Seg/Dom

### `services/price_analytics.py`

`get_telegram_report(ingredients, top_n=5)` → top N menores preços/ingrediente | `get_longitudinal_winners()` → lojas mais baratas (90d) agregado por dia | `get_price_trends(ingredient, days=90)` → avg/min/max ppk diário | `get_cross_ingredient_ranking(days=90)` → store_scores (top1/top3/total) | `generate_report_html(products, ingredients)` → HTML com tabela de melhores preços | **`otimizar_carrinho_compras(lista_itens, max_sources=2)`** → Monofonte (melhor loja única que cobre 100%) + Multifonte (combinação ≤N lojas, O(n²) combinações) + economia + formatação markdown/html

### `services/price_intelligence.py`

`get_historical_stats(ingredient, store)` → média/std/min/max/n | `detect_anomaly(ingredient, store, ppk)` → Z-score (threshold 2.0, severe >3.0) + Isolation Forest (contamination 0.1, n_estimators=50) + tags: PRECO_SUSPEITO/PRECO_ELEVADO/OFERTA_REAL/NORMAL/SEM_HISTORICO | `enrich_prices(prices)` → batch processing com cache joblib TTL 7d

### `services/review_queue_service.py`

`insert_review_item(item)` → INSERT com dedup por (store_name, raw_product) | `get_review_queue(limit=500)` → ORDER BY collected_at DESC | `approve_review_item(id, ingredient_id, brand_override)` → resolve ingrediente (exato→fuzzy≥70) → upsert → auto-aprender alias se semântica ≥0.75 | `reject_review_item(id)` → status=rejected | `auto_reject_stale_review_items(max_age=7d, min_confidence=0.6)` → rejeita itens pending velhos com baixa confiança

### `services/collector.py`

`load_ingredients()` / `load_stores()` → ativos + scrape_frequencies habilitados | `build_product_entry()` → monta PriceEntry completo com normalized + brand + weekday + promo detection | `process_price_match(store, product, price, unit, ingredients)` → pipeline completo: keywords→exclude→match→normalizer→brand→semantic→llm→review/upsert | `_auto_disable_if_needed(store, threshold=3)` → se últimas 3 coletas falharam, desativa loja | `_check_zero_products_alert(store, threshold=3)` → alerta se 3 coletas seguidas com 0 produtos | `_collect_generic(stores, scraper_cls, ingredients, label)` → genérico com per-ingredient filter + thumbnail + log + auto-disable | `collect_tier1_pdfs()` → filtra por publish_day + quinta | `collect_extra_flyers()` / `collect_pao_flyers()` / `collect_tier1_api_flyers()` / `collect_tier2_vtex()` / `collect_tier3_websites()` / `collect_carrefour()` / `collect_tier2_js()` / `collect_aggregators_ssr()` / `process_ocr_queue()`

### `parsers/`

| Função | Descrição | Onde |
| :--- | :--- | :--- |
| `normalize_price(price, unit)` | 3 weight patterns + 4 unit patterns → qty/unit_kg/total_kg/ppk/pun | `normalizer.py` |
| `match_ingredient(product, ingredients, threshold=80)` | exato → alias → fuzzy token_set_ratio | `matcher.py:65` |
| `rank_ingredients(product, ingredients, top_n=3)` | Ranking completo com scores + tipos | `matcher.py:109` |
| `extract_brand(product, ingredient)` | 3 níveis: word boundary → substring → fuzzy ≥80% | `brand_extractor.py:18` |
| `SemanticMatcher.get_similarity(product, ingredient)` | Cosseno embeddings ONNX (multilingual MiniLM) | `semantic_matcher.py:96` |
| `SemanticMatcher.combined_score(fuzz, sem)` | 0.6×(fuzz/100) + 0.4×sem | `semantic_matcher.py:127` |
| `LLMClassifier.classify_sync(product, candidates)` | Cache SHA-256 → Groq → OpenRouter → HF → fallback | `llm_classifier.py:67` |

### `services/price_service.py` (Facade)

Reexporta: upsert_price, search_prices, get_prices_for_ingredient, get_latest_prices, get_price_history, insert/approve/reject_review_item, get_telegram_report, get_longitudinal_winners, get_price_trends, get_cross_ingredient_ranking, get_cheapest_prices, cleanup_old_prices, cleanup_old_logs, cleanup_old_flyers_all, cleanup_resolved_review_items, log_scraper_run, upsert_recipe

### RPCs do Supabase (7)

| RPC | Descrição | Onde |
| :--- | :--- | :--- |
| `upsert_price_rpc(19 params)` | INSERT ON CONFLICT DO UPDATE, SECURITY DEFINER | `consolidated.sql:719` |
| `exec_sql(sql)` | Executa DDL/SQL arbitrário, SECURITY DEFINER | `consolidated.sql:947` |
| `exec_sql_query(sql)` | SELECT → JSON array, SECURITY DEFINER | `consolidated.sql:959` |
| `cleanup_old_prices(90d)` | TTL prices + price_history | `consolidated.sql:527` |
| `cleanup_old_logs(30d)` | TTL scraping_logs | `consolidated.sql:973` |
| `cleanup_old_flyers_all(180d)` | TTL flyers | `consolidated.sql:918` |
| `cleanup_resolved_review_items(30d)` | TTL review_queue resolvidos | `consolidated.sql:930` |

---

## 📋 7. REGRAS DE NEGÓCIO

### 7.1. Coleta (Scraping)

| Regra | Detalhes | Onde | Prio |
| :--- | :--- | :--- | :--- |
| **ETag/MD5 Cache Hit** | HEAD → se ETag ou content-md5 inalterado, pula download | `base_flyer.py:93-104` | 🔴 |
| **OCR Fallback** | pdfplumber vazio → Tesseract (por, 300dpi, 2 threads) | `base_flyer.py:137-143` | 🟡 |
| **Retry Exponencial** | 3 tentativas com backoff 1s→2s→4s (max 30s) em HTTP errors/timeout | `base_web_scraper.py:14-33` | 🔴 |
| **Rate Limit** | Pausa configurável entre requisições (default 1s, por store) | `base_web_scraper.py:65` | 🟡 |
| **Filtro Food/Non-Food** | Tiendeo: 7 FOOD keywords, 18 NON_FOOD (farmácia, pet, magazine) | `aggregator_scraper.py:20-42` | 🟡 |
| **Auto-Disable de Loja** | 3 falhas consecutivas → `is_active=False` + log warning | `collector.py:289-308` | 🟡 |
| **Alerta Zero Produtos** | 3 coletas seguidas com 0 itens → log warning | `collector.py:311-329` | 🟡 |
| **Filtragem por Ingrediente** | Scrapers desabilitáveis por ingrediente via feature flags (`features.scrapers.{scraper}.{ingredient}`) | `collector.py:356-359` | 🟠 |
| **Coleta por Dia da Semana** | Tier 1 PDF só coleta se `publish_day` da loja ou quinta-feira | `collector.py:492-496` | 🟡 |
| **Scrape On-Demand** | Telegram `/scrape <loja>` → INSERT scrape_requests → worker em ~15min | `handlers.py:156-187` | 🟢 |

### 7.2. Normalização de Preço

| Regra | Exemplos | Onde | Prio |
| :--- | :--- | :--- | :--- |
| **parse_unit()** | "cx 12x395g" → qty=12, unit_kg=0.395, total_kg=4.74 | `normalizer.py:45-68` | 🔴 |
| | "2kg" → qty=1, unit_kg=2.0 | | |
| | "500g" → qty=1, unit_kg=0.5 | | |
| | "12un 395g" → qty=12, unit_kg=0.395 | | |
| **price_per_kg** | `round(raw_price / total_kg, 4)` → to_dict() arredonda 2 casas | `normalizer.py:81-85` | 🔴 |
| **price_per_un** | `round(raw_price / qty, 4)` | `normalizer.py:86` | 🔴 |
| **Detecção Promoção** | Regex: "promo", "oferta", "desconto", "N% off" | `price_repository.py:23-27` | 🟡 |
| **Validade Default** | NOW() + 7d; extraída via regex do texto | `price_repository.py:28-31` | 🟡 |

### 7.3. Calculadora de Receitas

| Regra | Lógica | Onde | Prio |
| :--- | :--- | :--- | :--- |
| **Monofonte** | Para cada loja, testa se cobre 100% da lista. Melhor = menor total. | `price_analytics.py:217-249` | 🔴 |
| **Multifonte** | Combinações de ≤N lojas (default 2). Escolhe mais barata por ingrediente. O(n²). | `price_analytics.py:254-295` | 🔴 |
| **Overhead + Lucro** | yield_qty=40, overhead_pct=15%, profit_pct=300% | `consolidated.sql:787-788` | 🟡 |
| **Item sem preço** | Se ingrediente sem preço → "sem preço" em ambos cenários | `price_analytics.py:198-210` | 🟡 |

### 7.4. Qualidade + Cleanup

| Regra | Detalhes | Onde | Prio |
| :--- | :--- | :--- | :--- |
| **Dedup** | UNIQUE (ingredient_id, store_id, collected_at) ON CONFLICT DO UPDATE | `consolidated.sql:625-647` | 🔴 |
| **Trigger price→history** | AFTER INSERT OR UPDATE → copia com ON CONFLICT | `consolidated.sql:215-250` | 🔴 |
| **Auto-reject stale** | Itens pending >7d com confiança <0.6 → rejected | `review_queue_service.py:213-227` | 🟡 |
| **Cleanup prices 90d** | TTL via RPC | `main.py` | 🟡 |
| **Cleanup logs 30d** | | | 🟢 |
| **Cleanup flyers 60d/180d** | OCR failed / ALL | | 🟢 |
| **Cleanup revisão 30d** | Resolvidos | | 🟢 |
| **Release mensal** | 1º dia: snapshot .json.gz no GitHub Releases | `.github/workflows/scrape.yml` | 🟢 |

### 7.5. Flyer Service

| Regra | Detalhes | Onde | Prio |
| :--- | :--- | :--- | :--- |
| **Thumbnail Upload** | PNG da 1ª página do PDF enviado ao Supabase Storage (`flyers/{store}_{date}.png`) | `flyer_service.py:43-59` | 🟢 |
| **Flyer Upsert** | INSERT com ON CONFLICT (store_name, region, image_hash) para dedup | `flyer_service.py:62-92` | 🟡 |
| **OCR Status Tracking** | pending → done/failed com contagem de produtos extraídos | `flyer_service.py:95-131` | 🟡 |
| **Non-Food Cleanup** | Deleta flyers de lojas não-alimentícias (40+ keywords: boticário, magazine, pet, etc.) | `flyer_service.py:160-233` | 🟡 |
| **Cleanup Alert** | Se cleanup deleta 0 linhas por 3+ dias consecutivos → log warning | `flyer_service.py:27-40` | 🟢 |

### 7.6. Importação Manual

| Regra | Detalhes | Onde | Prio |
| :--- | :--- | :--- | :--- |
| **Import CSV/XLSX** | Importa planilhas com colunas: ingredient, store, price, unit, collected_at, brand | `import_service.py:14-73` | 🟡 |
| **Validação** | Ingrediente e loja precisam existir no DB; preço > 0; formato suportado: .csv/.xls/.xlsx | `import_service.py:42-47` | 🟡 |
| **Tier auto** | Se store contém "Manual" → tier 4, senão tier 2 | `import_service.py:61` | 🟢 |

### 7.7. Telegram Bot (6 comandos)

| Comando | Função | Onde |
| :--- | :--- | :--- |
| `/preco <ing>` | `startswith` no canonical_name → top 10 com 🥇🥈🥉 e R$/kg | `handlers.py:39-80` |
| `/lista` | Ingredientes por categoria | `handlers.py:83-102` |
| `/status` | Última coleta, total preços, lojas, confiáveis ≥80% | `handlers.py:105-122` |
| `/scrape <loja>` | Enfileira coleta via scrape_requests | `handlers.py:156-187` |
| `/start` | Boas-vindas + comandos | `handlers.py:125-136` |
| `/ajuda` / `/help` | Ajuda detalhada | `handlers.py:139-153` |

### 7.8. Alertas

| Regra | Detalhes | Onde | Prio |
| :--- | :--- | :--- | :--- |
| **Triggers** | `price_drop`, `new_low_price`, `daily_report`, `scrape_failure`, `review_queue_threshold` | `consolidated.sql:453` | 🟡 |
| **Canais** | `email`, `telegram`, `whatsapp` (CHECK constraint) | `consolidated.sql:429` | 🟡 |
| **Frequência** | Configurável por regra (default 1440 min) | | 🟢 |
| **Destinatários** | Array UUIDs → alert_recipients | `consolidated.sql:462` | 🟡 |
| **Price Drop ≥10%** | Calcula média 30d histórica; se queda ≥10% → notifica | `alert_service.py:27-46` | 🟡 |
| **Scrape Failure (1h)** | Busca erros na última hora nos scraping_logs | `alert_service.py:107-131` | 🟡 |

### 7.9. Segurança

| Regra | Detalhes | Onde | Prio |
| :--- | :--- | :--- | :--- |
| **RLS service_role** | Full access em todas as tabelas de config | `consolidated.sql:506-512` | 🔴 |
| **RLS anon** | SELECT only em tabelas públicas | `consolidated.sql:515-521` | 🔴 |
| **RLS prices** | anon SELECT, service_role INSERT/UPDATE | `consolidated.sql:190-192` | 🔴 |
| **SECURITY DEFINER** | RPCs rodam como criador (bypass RLS) | `consolidated.sql:776` | 🔴 |
| **Auth TOTP** | Dashboard com senha + 2FA | `dashboard/login_page.py` | 🟡 |
| **Circuit Breaker LLM** | 3 falhas consecutivas → cooldown 10 min | `llm_strategies.py:50-58` | 🟡 |
| **Rate Limiter** | SQLite-based para login e Telegram | `services/rate_limiter.py` | 🟢 |

### 7.10. Dependências entre Regras

- **Normalização (7.2)** é pré-requisito para **Cálculo de Preço por KG (7.2)**
- **Matching (8.1)** define o `ingredient_id` necessário para **Materialized View (4.2)** e **Calculadora (7.3)**
- **Inteligência (8.3)** alimenta a **Review Queue (8.1)** quando anomalia é extrema
- **Service Role (7.9)** é a única permissão que permite ao **Scraper (7.1)** escrever no banco
- **Feature Flags (1.1)** controlam a **Filtragem por Ingrediente (7.1)**

### 7.11. Regras Implícitas (suposições do código)

- Moeda é sempre BRL — não há conversão de câmbio
- Validade default 7 dias se não encontrada
- Região prioritária: São Paulo / Baixada Santista
- Preço zero ou negativo é ignorado (`normalizer.py:76`)
- Palavras <3 caracteres são ignoradas em keywords (`matcher.py:15`)

---

## 🤖 8. PIPELINE DE IA

### 8.1. Pipeline de Matching (6 Estágios)

```
Produto bruto → [1] Normalizer → [2] Match Exato (100%) → [3] Fuzzy (≥80%) → [4] Blend (55-79%) → [5] LLM (65-80%) → [6] Review Queue (<55%)
```

| Estágio | Threshold | Ação | Onde |
| :--- | :--- | :--- | :--- |
| **Exato** | canonical_name ou alias contido → 100% | ✅ Upsert imediato | `matcher.py:49-62` |
| **Palavras** | Todas palavras do canonical (≥2) presentes → 100% | ✅ Upsert imediato | `matcher.py:59-61` |
| **Fuzzy** | RapidFuzz `token_set_ratio` ≥80% | ✅ Upsert imediato | `matcher.py:68-88` |
| **Blend Semântico** | 55-79%: `0.6×fuzz/100 + 0.4×embedding_similarity` | Reavalia score combinado | `semantic_matcher.py:127` |
| **LLM Classifier** | 65-80%: cache→Groq→OpenRouter→HF (3 falhas=circuit breaker 10min) | Decisão final com fallback | `llm_classifier.py:67` |
| **Review Queue** | <55% (ou < threshold configurável por ingrediente, default 0.55) | Revisão manual no dashboard | `collector.py:208-284` |

**Regras auxiliares do pipeline:**
- **Auto-aprender alias**: Ao aprovar item na review, se similaridade semântica ≥0.75, adiciona nome do produto como alias do ingrediente (`review_queue_service.py:149-173`)
- **Brand extraction**: 3 níveis — word boundary regex → substring regex → fuzzy palavra-a-palavra ≥80% (`brand_extractor.py:18-55`)
- **Exclude terms**: Se produto contém termo da `exclude_terms` do ingrediente, rejeita match (`matcher.py:42-47`)
- **Keyword pre-filter**: Antes do matching, verifica se produto contém ao menos uma keyword dos ingredientes (performance) (`collector.py` via `extract_all_keywords`)
- **Review threshold configurável**: Por ingrediente via `features.review_threshold` (default 0.55) (`collector.py:210-211`)

### 8.2. Modelos de ML Utilizados

| Modelo | Tipo | Uso | Onde |
| :--- | :--- | :--- | :--- |
| `paraphrase-multilingual-MiniLM-L12-v2` | Sentence-Transformer | Embeddings semânticos (CPU, ONNX) | `semantic_matcher.py:18` |
| `llama-3.3-70b-versatile` (Groq) | LLM | Classificação de match (primário) | `llm_strategies.py:117` |
| `mixtral-8x7b-instruct` (OpenRouter) | LLM | Classificação de match (fallback 1) | `llm_strategies.py:210` |
| `Mistral-7B-Instruct-v0.2` (HuggingFace) | LLM | Classificação de match (fallback 2) | `llm_strategies.py:287` |
| `Isolation Forest` (scikit-learn) | Anomaly Detection | Detecção de outliers de preço | `price_intelligence.py:107` |

### 8.3. Inteligência de Preços (Detecção de Anomalias)

| Regra | Condição | Tag | Onde |
| :--- | :--- | :--- | :--- |
| **Z-score > +2.0** | (ppk-mean)/std > 2 | PRECO_ELEVADO (severity medium) | `price_intelligence.py:83` |
| **Z-score > +3.0** | | PRECO_ELEVADO (severity high) | |
| **Z-score < -2.0** | | PRECO_SUSPEITO (severity medium/high) | |
| **Z-score -1.0 a -2.0** | | OFERTA_REAL (não é anomalia) | `price_intelligence.py:98` |
| **Isolation Forest** | score < -0.5 + tag NORMAL → força PRECO_SUSPEITO | Contamination=0.1, n_estimators=50 | `price_intelligence.py:107` |
| **Sem histórico** | n < 3 | SEM_HISTORICO | `price_intelligence.py:62` |
| **IF mínimo** | Treina só com ≥10 pontos históricos | Cache joblib TTL 7d | `price_intelligence.py:158` |
| **Feature flag** | `features.ai.price_intelligence` → se False, desliga tudo | Configurável por YAML | `price_intelligence.py:80` |

### 8.4. Cache e Performance

| Componente | Tecnologia | TTL | Onde |
| :--- | :--- | :--- | :--- |
| **LLM Cache** | SQLite + SHA-256 | 30 dias | `llm_cache.py` |
| **LLM Match Cache (DB)** | Supabase table `llm_match_cache` | 30 dias (expires_at) | `004_add_llm_match_cache.sql` |
| **Embedding Cache** | Disco (.npy files) | Permanente (até flush manual) | `semantic_matcher.py:57-68` |
| **Isolation Forest Cache** | Disco (.joblib files) | 7 dias | `price_intelligence.py:29-41` |
| **Feature Flags** | YAML + LRU in-memory | Por request (reload manual) | `config.py:8-13` |
| **LLM Circuit Breaker** | In-memory | 3 falhas → 10 min cooldown | `llm_strategies.py:50-58` |

---

## 🧠 9. ANÁLISE CRÍTICA

### O Que Está BOM

1. **Arquitetura modular** — Service Layer + Repository + ABC/Template Method + Strategy + Singleton + Cache-Aside. Todos os padrões bem aplicados.
2. **Pipeline 6 estágios** — Exato → Alias → Fuzzy (RapidFuzz) → Embeddings ONNX → LLM (3 providers, Circuit Breaker, fallback) → Review. Sofisticação técnica real para um projeto de free tier.
3. **Tratamento de erros em cascata** — ETag→download, pdfplumber→OCR, RPC→table, Groq→OpenRouter→HF→fallback, INSERT→ON CONFLICT. Cada camada tem fallback.
4. **Otimizador de Carrinho** — Monofonte/Multifonte com formatação markdown+HTML. Útil e bem implementado.
5. **Observabilidade** — OpenTelemetry, structlog (logging estruturado), capacity planning do free tier, health checks, benchmarks.
6. **Qualidade do banco** — 50+ índices, materialized view, UNIQUE constraints com dedup, RLS em todas as tabelas, triggers de auditoria.

### O Que Precisa Melhorar

| # | Problema | Onde | Risco |
| :--- | :--- | :--- | :--- |
| 1 | SERVICE_ROLE_KEY no dashboard | `price_repository.py:8` chamado pelo Streamlit | 🔴 CRÍTICO |
| 2 | exec_sql_query sem sanitização | `consolidated.sql:959` | 🔴 CRÍTICO |
| 3 | Testes desatualizados | pytest unit status "pending update" | 🟠 ALTO |
| 4 | Sem cache em consultas do dashboard | `dashboard/pages/` | 🟡 MÉDIO |
| 5 | Normalizer sem fallback | `normalizer.py:91` — se parse_unit falha, perde produto | 🟡 MÉDIO |
| 6 | Busca Telegram só startswith | `handlers.py:52` — "/preco condensado" não acha | 🟡 MÉDIO |
| 7 | Migrations duplicadas | consolidated vs 002/003/004 avulsos | 🟡 MÉDIO |

### O Que Está FALTANDO (sugestões de melhoria)

| Lacuna | Sugestão | Onde implementar |
| :--- | :--- | :--- |
| **Peso Mínimo** | Ignorar produtos com unit_kg < 0.01 (ex: 1g distorce média) | `normalizer.py` |
| **Conflito de Fontes** | Quando mesma loja informa preços diferentes p/ mesmo produto no mesmo dia | `price_repository.py` |

### Plano de Ação

| Prio | Ação | Esforço | Ganho |
| :--- | :--- | :--- | :--- |
| 🔴 | Criar role `dashboard_user` (sem service_role) | 2-3d | Elimina risco crítico |
| 🔴 | Sanitizar ou remover `exec_sql_query` | 1d | Elimina injeção SQL |
| 🟡 | Atualizar testes unitários | 3-5d | README volta a refletir realidade |
| 🟡 | Cache LRU em dashboard_queries (TTL 5min) | 2d | Dashboard mais rápido |
| 🟡 | Melhorar busca Telegram (fuzzy no lugar de startswith) | 1d | UX melhor |
| 🟡 | Fallback de unidade no normalizer (ex: "un" se kg falha) | 1d | Mais produtos aproveitados |
| 🟡 | Implementar regra de Peso Mínimo | 0.5d | Evita outliers |
| 🟢 | Testes para otimizar_carrinho_compras | 1d | Garantir feature nova |

### Ideias de Inovação (3)

1. **Push notification de "menor preço histórico"** — 80% já existe (alert_rules + price_intelligence + Telegram). Só conectar o trigger.
2. **Recomendação de substituição** — "Moça está R$5 mais caro que Piracanjuba hoje". Dados de marca + preço já existem.
3. **Calculadora de lote econômico** — Vale a pena comprar o pack? Usar o normalizer que já calcula R$/kg.

### Veredito Final

| Critério | Nota |
| :--- | :--- |
| Arquitetura | 9/10 |
| Código | 8/10 |
| Testes | 5/10 ↓ |
| Segurança | 6/10 ↓ |
| Performance | 8/10 |
| UX/Produto | 8/10 |
| Documentação | 9/10 |
| **Nota Final** | **8.0/10** |

**Recomendação: ✅ MANTER E CORRIGIR** — Projeto maduro, bem arquitetado, pipeline de matching sofisticado para um projeto free tier. Problemas são corrigíveis e concentrados em segurança da service_role + testes desatualizados. Nada que justifique rewrite.

---

## 📜 10. HISTÓRICO DE VERSÕES

| Versão | Data | Autor | Mudanças |
| :--- | :--- | :--- | :--- |
| — | 27/06/2026 | IA | Correção de discrepâncias: test counts (16→417, 93→94, 12→100, 2→0, 2→6), migration (987→861 linhas, 17→20 fases), scrapers (17→18 + roldao_flyer_scraper), services (21→23), scripts (~35→39), line counts (177→154, 208→154), Python version (3.11→3.11/3.13), workflow restore→restore-test, +001_config_tables.sql. (Nota: Python atualizado para 3.12 em 27/06/2026) |
| — | 27/06/2026 | Eric | Python 3.11 → 3.12 unificado (runtime.txt, CI, mypy, Ruff). Docs e workflows sincronizados. |
| — | 27/06/2026 | IA | Consolidado em arquivo único vivo (`CUSTO_DOCE_RAIO_X.md`). v2.0 removido. Changelog mantido inline. |
| v2.0 | 27/06/2026 | IA | Reestruturação: antiga Seção 7 dividida em "Regras de Negócio" (7) e "Pipeline de IA" (8). Adicionado 8.2 (Modelos ML), 8.4 (Cache), 10 (Histórico). |
| v1.0 | 27/06/2026 | IA | Criação do documento completo baseado na análise de 250+ arquivos. |
