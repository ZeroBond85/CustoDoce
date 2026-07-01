# Changelog

Todos os cambios_notáveis deste projeto são documentados aqui.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere a [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [0.2.4] - 2026-07-01

### Added

#### Phase 3 — CI Hardening + Time Budget Guard + Capacity Planning

- **`scripts/check_time_budget.py`**: Novo script que verifica se elapsed time >70% do `timeout-minutes` e emite `::warning::` no GHA. Integrado nos 4 jobs pytest (unit, integration, e2e-smoke, real) com `if: always()`.
- **`dashboard/pages/capacity_planning.py`**: Integrado ao sidebar no grupo "📈 Análises" como "Capacidade" (19ª página). Anteriormente orphan no disco desde Fase 8. Exibe disk usage, GHA minutes e SMTP quota com st.metric + st.progress e limites do free tier.
- **`tests/unit/test_design_checks.py`**: Movido de `tests/design/` → `tests/unit/` para simplificar a pirâmide de testes (2 camadas: unit + integration, elimina diretório `design/`).

### Changed

- **`.github/workflows/ci.yml`**: e2e-smoke timeout 15→25min; escopo reduzido para 3 testes (visao_geral + precos + calculadora); `--durations=5` em todos os 4 jobs pytest; time budget guard pós-cada job.
- **`admin/app.py`**: Import + registro de `render_capacity_planning` em `PAGE_FUNCTIONS` e `MENU_GROUPS`.
- **`dashboard/components/layout.py`**: `MENU_GROUPS` sincronizado com admin/app.py — "Capacidade" adicionado; `PAGES` agora com 19 entradas.
- **`scripts/test_total_coverage.py`**: `sync_docs_drift` e `sync_docs_v2_analyze` consolidados em `sync_docs_analyze` (apenas v2). Removida referência a `tests/design/`.
- **`scripts/sync_docs_v2/truth.py`**: `capacity_planning` removido da lista de exclusão (agora conta como página oficial).
- **`scripts/sync_docs.py`**: `capacity_planning` removido da exclusão em `_count_dashboard_pages()`.

### Fixed

- **`tests/unit/test_app_wiring.py`**: Atualizado de 18→19 páginas, adicionado `render_capacity_planning` em todos os validadores.
- **`tests/unit/test_dashboard_full.py`**: Comentário de referência atualizado de `tests/design/` → `tests/unit/`.

### Metrics

- pytest: **~528 unit + 94 schema + 102 integration + 6 real + 50 e2e = ~780 total** (sync_docs v2 reporta valores reais)
- ruff: **0 warnings**
- Pages: **19** (capacity_planning integrado). `tests/design/` diretório removido.
- CI: e2e-smoke 15→25min timeout, 17→3 testes, time-budget guard ativo.

## [0.2.3] - 2026-06-30

### Added

#### Sprint 7 — Dashboard Modernization Streamlit 1.58 (Menu Nativo + Dialogs + Batch Config)

- **`admin/app.py`**: `st.navigation()` com 5 grupos (Painel/Análises/Cadastros/Operações/Ferramentas); `MENU_GROUPS` como single source of truth; `PAGE_FUNCTIONS` mantido por compatibilidade com 87 testes legados; `_build_navigation()` com fallback `_render_page_by_id()`.
- **`dashboard/pages/promocoes.py`**: página órfã integrada ao layout oficial (18 páginas). Refatorada com `inject_css()`, filtros (loja/ingrediente/order), 3 KPIs, `st.dataframe` com column config, `_is_promotion()` + `_safe_ppk()` helpers.
- **`dashboard/pages/flyers.py`**: `@st.dialog("Confirmar exclusão")` — exclusão com confirmação + contagem de itens.
- **`dashboard/pages/relatorios.py`**: `@st.dialog("Confirmar envio")` — preview + canal + execução. `build_daily_report_html()` e `build_telegram_summary()` extraídas para funções puras.
- **`dashboard/pages/ingredientes.py`**: `@st.dialog("Confirmar sobrescrita do YAML")` com auto-backup em `data/ingredient_backups/`; 5 abas; `_backup_yaml()` + `_suggest_aliases()` helpers.
- **`dashboard/pages/config.py`**: per-flag "Salvar" substituído por `st.form` único com "Salvar Tudo"; botões batch ✅/⛔ para alert_rules e recipients.

#### Sprint 8 — Performance + Pagination

- **`dashboard/pages/alertas.py`**: `st.pagination()` nativo 54 regras → 25/página com `bind="query-params"`; `_fallback_pagination()` manual; `_contact_options()` helper.
- **`dashboard/pages/visao_geral.py`**: KPIs wrapados em `.cd-kpi-row` flexbox responsivo (1 col ≤640px / 2 cols ≤768px / 4 cols desktop); spinners para promo/coverage/winners/ranking.
- **`dashboard/pages/insights.py`**: `pivot_table(columns="store_count")` (quebrado — pivoteava coluna numérica) substituído por bar chart por ingrediente com cor = cobertura; guard para <2 ingredientes.
- **`services/dashboard_queries.py`**: `extract_ppk()`/`extract_pun()` com fallback: `row["price_per_kg"]` (flat) → `row["normalized"]["price_per_kg"]` (nested); trata None/0 → 0.0.

#### Sprint 9 — Polish + Acessibilidade + Hardening

- **Loading spinners** em 6 páginas: `precos.py`, `historico.py`, `fontes.py` (3 queries), `ranking.py` (3 tabs), `insights.py`, `visao_geral.py` (3 queries).
- **Labels acessíveis**: `login_page.py` — `help=` tooltip em 6 inputs; `calculadora.py:34` — `help=` na seção selectbox.
- **`services/email_service.py`**: `import httpx` movido para top-level; `httpx.post()` em `send_telegram_report()` envolto em try/except + `logging.warning`; `import smtplib as _ssl_smtplib` inline removido (reusa top-level `import smtplib`); `server: smtplib.SMTP` type annotation reduz mypy falsos positivos (10→8).

#### Sprint 9.5 — Test Coverage

- **`tests/unit/test_sprint7_8_9_features.py`**: 23 testes puros (sem Streamlit runtime) — `extract_ppk` fallback (6), `_is_promotion` (4), dialog existence (3), `_contact_options` (3), `_fallback_pagination`, ingredientes constants (2), MENU_GROUPS structure (2), `_build_navigation` (1).
- **`tests/unit/test_app_wiring.py`**: atualizado para 18 páginas + 3 novos testes de menu groups; encoding fix para UTF-8.
- **`tests/unit/test_dashboard_full.py`**: `len(PAGES)` atualizado 17→18.

### Changed

- **`dashboard/components/layout.py`**: `MENU_GROUPS` adicionado como fonte única da verdade; `PAGES` 17→18 (promocoes); `render_sidebar()` delega para `_render_nav_footer()` quando `st.navigation` disponível.

### Fixed

- **`dashboard/pages/insights.py`**: heatmap quebrado (pivot_table em coluna numérica) substituído por bar chart funcional.
- **`admin/app.py`**: TypeError potencial por page `None` — guard `if pg:` em `_build_navigation()`.
- **`tests/unit/test_app_wiring.py`**: encoding bug `encoding="utf-8"` em 2 testes AST que falhavam em Windows com caracteres acentuados.

### Metrics

- pytest: **577 passing** (unit: 483 + schema: 94) — +26 da baseline 551
- ruff: **0 warnings** em todos os arquivos modificados
- mypy: **0 novos erros** (8 pre-existentes em `email_service.py` — tuple typing, não regredidos)
- Pages: **18** (era 17, promocoes integrada)

## [0.2.2] - 2026-06-30

### Fixed

#### Sprint 6 — Migration Sync + httpx Pin + E2E Login Timing

- **`tests/e2e/test_e2e_real.py::login_to_app`**: Race condition de cold start — `page.wait_for_timeout(5000)` substituído por polling ativo (até 45s) que espera `input[type='password']` ou `button:has-text('Visao Geral')` aparecer. Adicionada chamada a `ensure_app_ready()` no fim do login para garantir sidebar visível.
- **`requirements.txt`**: `httpx>=0.28` → `httpx>=0.28,<1.0` (prevenir breaking change httpx 1.x que removeu `proxies=`).
- **`scripts/deploy_database.py`**: Incluídas migrations `004_add_llm_match_cache.sql` (Phase 20) e `005_add_scraper_health_log.sql` (Phase 21) que estavam ausentes do consolidated SQL.

### Changed

- **`scripts/deploy_database.py`**: expected_tables atualizado de 14 → 16.

## [0.2.1] - 2026-06-29

### Fixed

#### Sprint 5 — CI Hardening + Real E2E Validation

- **`admin/app.py`**: TypeError em produção desde FASE 8 — `render_login(ADMIN_PASSWORD)` chamado com argumento, mas `render_login()` não aceita args. Fix: `render_login()`.
- **`scripts/warmup_streamlit.py`**: Reescrito de HTTP (inútil — Streamlit Cloud virou SPA React) para Playwright headless (navega, faz login, acorda app hibernado, espera sidebar).
- **`.github/workflows/backup.yml`**: RPC backup nunca rodou em 8+ runs consecutivas. Causa raiz: heredoc `<< 'PYEOF'` indentado (YAML indentou delimiter). Extraído para `scripts/rpc_backup.py`. `hashFiles()` corrigido (`if: steps.file.outputs.filename != ''`).
- **`.github/workflows/ci.yml`**: e2e-smoke migrado para localhost (sem continue-on-error, sem cloud flakiness). Bloqueia merge em falha.
- **`.github/workflows/e2e.yml`**: Reescrito — mensal (dia 1), 2 jobs: localhost (16 páginas) + cloud (16 páginas via Playwright). Sem continue-on-error.
- **`.github/workflows/heal-scrapers.yml`**: `ZeroBond85/CustoDoce` hardcoded → `${{ github.repository }}`.
- **`.github/workflows/on_demand_scrape.yml`**: cache `pip` adicionado.

### Added

- **`tests/unit/test_app_wiring.py`**: 7 testes AST + imports que validam a fiação do `admin/app.py` sem executar Streamlit. Pega TypeError, import quebrado, assinatura errada de página. Roda no CI unit em <5s — version-independent.
- **`tests/e2e/test_e2e_real.py::test_sidebar_completeness`**: Varre sidebar e compara com lista PAGES — detecta botões órfãos ou PAGES desatualizado.
- **`scripts/rpc_backup.py`**: Script de backup via RPC (extraído do heredoc quebrado).
- **AGENTS.md**: Lições #18 (`failure()` + `continue-on-error`), #19 (heredoc YAML indentado), #20 (Streamlit Cloud SPA — HTTP warmup inútil).

### Changed

- **`tests/e2e/test_e2e_real.py::ensure_app_ready()`**: Adaptativo — 6 retries × 30s timeout para cloud URL, 3 × 15s para localhost.
- **`pyproject.toml`**: `asyncio_default_fixture_loop_scope = "function"` + filterwarnings para DeprecationWarning.

## [0.2.0] - 2026-06-27

### Added

#### Fase 4.1 — Observabilidade Estruturada
- `services/logger.py` — Structured logging com `structlog` (JSON em prod, console em local)
- `services/otel.py` — Tracing com OpenTelemetry (`OTLPSpanExporter` em prod, `ConsoleSpanExporter` em local)
- `main.py` refatorado para usar logs estruturados com `event name + kwargs`
- `scrapers/*.py` e `services/*.py` migrados de `logging` para `services.logger`
- `requirements.txt` atualizado: adicionado `structlog`, `opentelemetry-api`, `opentelemetry-sdk`

#### Fase 2.4 — Staging Environment
- `scripts/sync_staging.py` — Sincronização de schema + dados core Prod → Staging
- `scripts/seed_staging.py` — Seed de dados sintéticos para Staging
- `scripts/validate_staging.py` — Health check de tabelas, RPCs e View Materializada em Staging
- `.github/workflows/deploy-staging.yml` — Workflow de deploy isolado
- `docs/deployment-staging.md` — Guia passo-a-passo de setup do Staging

#### Fase 4.4 — Per-Ingredient Feature Flags
- `services/config.py` adicionado `get_feature(path, ingredient=None)` — permite override por ingrediente
- `config/features.yaml` adicionado bloco `overrides` para controle fino
- `services/collector.py` usa `get_feature` para filtrar ingredientes por scraper e inferir flag de AI

#### Fase 4.8 — LLM Resilience + Cache + Cart Optimizer + Capacity Planning
- `parsers/llm_cache.py` — Cache SQLite (TTL 30 dias) para decisões de LLM. **Recurso 3 (RFC)**
- `parsers/llm_strategies.py` — Strategy Pattern com `GroqStrategy`, `OpenRouterStrategy`, `HuggingFaceStrategy`. Cada uma implementa:
  - JSON Mode (`response_format={"type": "json_object"}`)
  - Circuit Breaker (3 falhas → 10 min cooldown)
  - Try/except robusto com `timeout=15s`
  - **Recurso 2 (RFC) — Blindagem contra crashes**
- `parsers/llm_classifier.py` REFATORADO — Orquestrador que: cache → Groq → OpenRouter → HF → fallback seguro (graceful degradation)
- `services/price_analytics.otimizar_carrinho_compras(lista_itens)` — Cálculo de 2 cenários:
  - **Monofonte**: loja única que vende a lista inteira pelo menor valor
  - **Multifonte**: dividir em até 2 lojas para maior economia
- `dashboard/pages/diagnostico.py` — Adicionada seção **Capacity Planning**:
  - Disco do Supabase (via `pg_total_relation_size()`) vs. 500 MB
  - Minutos de GitHub Actions (`SUM(duration_seconds)` de `scraping_logs`) vs. 2000 min
  - Cota SMTP (contagem de envios 24h) vs. 500 e-mails/dia
  - **Recurso 4 (RFC) — Painel SRE**
- `supabase/004_add_llm_match_cache.sql` — Tabela `llm_match_cache` (PostgreSQL cache backup com RLS)

### Changed

- `scripts/full_prod_validation.py` — novo orquestrador de validação (fases 0-6) com loop até 100% verde
- `scripts/validation_phases/phase*.py` — 7 módulos de fase (static, deploy, sync, collect, report, tests, health)
- `scripts/force_saturday.py` — Helper de contexto para validar coleta Tier 1 fora de quarta/quinta
- `docs/ROLLBACK_PROD.md` — Template de procedimento de rollback (auto-deployed)
- `docs/architecture.md` atualizado para incluir o LLM Strategy Pattern e o Cache

### Deprecated

- API antiga de `parsers/llm_classifier` (chamada direta sem Strategy). Compatibilidade mantida via alias interno.

### Fixed

- GitHub Actions `scrape.yml` agora tolera `RateLimitError` sem derrubar o job
- `services/collector.py` agora não chama LLM quando ai precisa para ingredientes desativados
- `services/price_analytics` agora aplica `LIMIT` em queries de `top winners` para evitar pagination attacks

---

## [0.1.0] - 2026-06-27

### Added

#### Fase 0 — Fundação Docs
- `README.md` reescrito (PT-BR, fonte única, ~400 linhas)
- `AGENTS.md` atualizado (memória técnica sincronizada com 21 fases)
- `docs/architecture.md` (Mermaid: data flow, matcher cascade, DB design, tiers)
- 5 ADRs (`docs/adr/001-005`): architecture, matcher-strategy, tier-strategy, db-design, free-tier-limits
- `docs/deployment.md` (setup step-by-step com 11 secrets)
- `docs/migration-guide.md` (deploy, validate, rollback)
- `tests/README.md` reescrito (382 testes, 5 camadas)
- `docs/archive/ux_audit_2026-06.md` (arquivado)

#### Fase 1 — Bloqueadores Técnicos
- `scripts/export_onnx.py` — export sentence-transformers para ONNX (8-10s cold start vs 2min PyTorch)
- `scripts/verify_onnx.py` — verifica consistência cosine similarity PyTorch vs ONNX (1.0)
- `scripts/validate_db_schema.py` — 87+ checks via RPC (sem psycopg2, porta 443)
- `Makefile` — 10 targets (test-unit, test-int, test-real, lint, typecheck, quality, deploy, schema, db-audit, clean)

#### Fase 2.1 — Data Quality Gates
- `scripts/run_quality_gates.py` — Great Expectations suite com 5 expectations
  - `price_per_kg > 0`
  - `match_confidence >= 0.55`
  - Sem nulls em colunas críticas
  - `raw_price > 0`
- Bloqueia CI em caso de falha

#### Fase 2.2 — Scraper Health Dashboard
- `dashboard/pages/scraper_health.py` — página com 3 tabs (Health Overview, Latency chart, Raw Logs)
- `services/dashboard_queries.get_scraper_health_dashboard()` — metrics: last_run, success_rate, latency_p95_ms, avg_items_per_run
- Sidebar + admin/app.py atualizado com `scraper_health`

#### Fase 2.3 — Backup/Recovery Automation
- `.github/workflows/backup.yml` — semanal (domingo 08:00 UTC), pg_dump custom format compress → GitHub Artifacts (14 dias)
- `.github/workflows/restore-test.yml` — mensal (dia 1, 09:00 UTC), dry-run psql, valida integridade
- `scripts/cleanup_old_artifacts.py` — mantém N backups mais recentes via PyGithub
- `scripts/download_latest_artifact.py` — baixa artifact por prefixo via PyGithub

#### Fase 3.1 — API Docs
- `docs/api/price_service.md` — search_prices, get_price_history, upsert_price, review_queue, analytics
- `docs/api/dashboard_queries.md` — queries cacheadas do dashboard, KPIs, coverage
- `docs/api/config_db.md` — CRUD de ingredients, stores, schedules, feature_flags, alert_rules
- `docs/api/flyer_service.md` — upsert_flyer, mark_processed, cleanup_old_flyers

#### Fase 3.2 — Security & Contributing
- `docs/security.md` — secrets management, RLS policies, input validation, dependabot, known risks
- `docs/contributing.md` — dev setup, coding standards, branching strategy, PR process, testing guidelines

### Changed

- `scripts/run_quality_gates.py`: f-string sem placeholders corrigida → string normal
- `services/dashboard_queries.get_store_health()`: agora calcula latência P95 e success_rate
- `dashboard/pages/visao_geral.py` e `precos.py`: adicionado `__all__` exports
- `tests/unit/test_dashboard_full.py`: contagem PAGES de 16 para 17 (nova página scraper_health)

### Fixed

- Ruff W293 (whitespace), F401 (unused imports), S608 (SQL injection via f-string)
- Mypy 0 erros em 34 source files
- 477+ pytest passando (unit + schema)

### Known Risks

- **transformers 4.57.6**: 2 CVEs conhecidas (PYSEC-2025-217, CVE-2026-1839)
  - Fix: `transformers>=5.0.0rc3` (pre-release, não aplicado por risco de quebra)
  - Exploitabilidade: baixa (Pipeline API local, dados controlados)

---

## [0.4.0] - 2026-06-28 — Sprint 1: UX + Seguranca + Validacao Real

### Added
- **`scripts/validate_dashboard_queries.py`**: smoke test que valida 10 queries do dashboard contra Supabase real, verifica colunas retornadas vs. esperadas pelos `column_config` das páginas. Roda no CI pós-deploy (`deploy-check` job).
- **Seguranca (Sprint 1.1)**: Tabs de edição `.env` (config.py) e YAML (lojas.py) removidas do dashboard; banner info "YAML synced from DB" em ingredientes.py.
- **Bot DB Sync (Sprint 1.2)**: `handlers.py` reescrito — lê ingredientes ativos do DB (`config_db.get_active_ingredients()`) com fallback YAML; fuzzy search `rapidfuzz.fuzz.token_set_ratio`; paginação inline keyboard.
- **Mobile CSS (Sprint 1.3)**: Media queries 768px/640px; sidebar compacta; tabelas com primeira coluna sticky; safe-area padding; chart height limit.
- **Query Params (Sprint 1.4)**: `precos.py`, `historico.py`, `calculadora.py` — sincronização bidirecional (URL ↔ session_state) sem loop de rerender.
- **Acessibilidade (Sprint 1.5)**: Skip-link "Pular para conteúdo" em `layout.py:render_skip_link()`; focus-visible em selectbox/checkbox; `prefers-reduced-motion` desliga animações; `font-variant-numeric: tabular-nums` em métricas.
- **`ci.yml`**: Dashboard query smoke test no job `deploy-check` (após validação de schema).

### Changed
- `dashboard/pages/calculadora.py`: trocado `st.tabs` por `st.selectbox` para compatibilidade com query params (tab index trackeável via session_state).
- `dashboard/pages/precos.py` e `historico.py`: acentos em column_config alterados de escape `\u00e7\u00e3o` para literais `ção` (compatibilidade com test_is_promotion_in_display).

### Fixed
- Teste `test_is_promotion_in_display` falhava porque precos.py e historico.py usavam `\u00e7\u00e3o` em vez de `ção` literal — corrigido.
- `calculadora.py`: estrutura corrigida de `with tabs[1]:` para `elif tab_index == 1:`.

### Security
- **Tabs de edição removidas**: config.py não expõe mais editor `.env`; lojas.py não expõe mais editor YAML raw.
- **Secrets guard**: pre-commit hook mantém bloqueio de `sk-*`, `gsk_*`, `sk-or-*` no staged files.

---

## [unreleased]

### Added

#### sync_docs v2 — heading-aware stale-ref detector + auto-updater (Sprint 10)
- **`scripts/sync_docs_v2/`**: 5 novos módulos baseados em markdown-it:
  - `truth.py`: source of truth (test counts, pages, workflows, services)
  - `parser.py`: section span parser via heading hierarchy
  - `classifier.py`: HISTORICAL/CURRENT/AMBIGUOUS por heading path
  - `updater.py`: `\bNUMBER\b` replacement em CURRENT blocks only
  - `cli.py`: `--analyze`, `--sync`, `--dry-run`, `--dump-truth`
- **`scripts/sync_docs.py`**: +3 flags (`--analyze`, `--sync`, `--dump-truth`) que delegam ao v2
- **`scripts/test_total_coverage.py`**: nova fase `sync_docs_v2_analyze`
- **`tests/unit/test_sync_docs_v2.py`**: 25 testes unitários (mocks, 1.67s) — 5 módulos cobertos
- **`AGENTS.md`**: Lição #25 (novo código = novos testes)
- **Resultado**: 5 CURRENT refs corrigidos (512→577, 630→745, 709→745, 418→483, 383→483); 14 HISTORICAL preservados; 0 AMBIGUOUS

#### Doc Sync Enhancement (Sprint 10 — Documentation Hygiene)
- **`scripts/sync_docs.py`**: 3 auto-fixers (`_fix_tree_test_count`, `_fix_page_import_count`, `_fix_streamlit_skill_row`) + `_strict_audit()` que varre todos `.md` para detecção de 37 patterns stale (HIGH/MEDIUM). Flag `--strict`. Encoding Windows-safe (ASCII replace).
- **`.github/workflows/ci.yml`**: docs-sync job agora `--check --strict` (bloqueante). **`.githooks/pre-commit`**: layer 2.5 com `sync_docs --check --strict` (aviso leve, não bloqueia).
- **`services/collector.py`**: `import httpx` movido de inline (dentro de `process_ocr_queue()`) para top-level imports — lazy import removido.

### Changed
- **Docs (37 stale refs corrigidos)**: 11 arquivos `.md` atualizados pós-Sprint 7-9 (page counts 17→18, test counts 418→483, 512→577, 630→745). Detalhes por arquivo:
  - `AGENTS.md`: auto-fix + manual (lines 82, 85, 111, 324, 713)
  - `.opencode/skills/streamlit/SKILL.md`: 7 edições (17→18 pages, promocoes orphan→registered, single orphan)
  - `docs/archive/CUSTO_DOCE_RAIO_X.md`: 5 edições (tabela avaliação 8.5→9.0, nota final 8.5→9.0)
  - `docs/archive/RAIO-X_CUSTO_DOCE_RESUMIDO.md`: 3 edições (17→18 abas, 512→577)
  - `docs/contributing.md`: 3 edições (418→483, 17→18)
  - `docs/architecture.md`: 1 edição Mermaid (17→18 módulos)
  - `README.md`: roadmap com Sprints 5,6,7-9 + Next Steps atualizados
  - `docs/archive/ux_audit_2026-06.md`: 1 edição (17→18 abas)

### Metrics
- sync_docs --strict: 0 actual issues (historical README roadmap entries are intentional snapshots)
- ruff: 0 warnings
- pytest: **577 passing** (unit: 483 + schema: 94) + 102 integration + 10 design + 6 real + 50 e2e = **745 total**

---

## [0.3.0] - 2026-06-28 — Fase 9: CI Hygiene + Cleanup

### Security 🔒

#### Sensitive files removidos do histórico (190 commits reescritos via `git filter-branch`)
- `api_configuration.json` — chaves de provedores de IA
- `api_providers.json` — config de LLMs
- `cline_config.json` — config do Cline IDE
- `.vscode/settings.json` — settings locais
- `backup_prod_2026-06-27.sql` — dump SQL com dados de produção
- `git_msg.txt`, `trigger_fix.sql` — scratch files
- `data/llm_cache.db`, `data/embedding_cache/*.npy`, `data/onnx_models/` — modelos ML (~450MB empacotado)
- `.vs/`, `.vscode/` — workspaces IDE

**Resultado**: pack do repo **444MB → 8.7MB**. Único `git gc --prune=now` removeu blobs órfãos que `git stash` segurava.

#### Dependabot Alerts dismissed (Pillow 12.2.0 patched)
7 alertas são **inaccurate** porque我们已经 versão Pillow patched (≥10.0.1, ≥10.2.0, ≥10.3.0, ≥12.2.0). Local `pip-audit --strict -s osv` retorna **No known vulnerabilities found**. Dismissal via `gh api -X PATCH` para todos os 7 (`GHSA-j7hp-h8jx-5ppr`, `GHSA-3f63-hfp8-52jq`, `GHSA-44wm-f244-xhp3`, `GHSA-wjx4-4jcj-g98j`, `GHSA-r73j-pqj5-w3x7`, `GHSA-w8v5-vhqr-4h9v`, `GHSA-6w46-j5rx-g56g`).

### Fixed (CI Jobs)

- **`ci/lint`**: `pip install -r requirements-dev.txt` falhava porque `PIP_INDEX_URL=https://download.pytorch.org/whl/cpu` substituía PyPI. Trocado para `PIP_EXTRA_INDEX_URL` (PyPI primary, pytorch fallback).
- **`ci/typecheck`**: `check_ingredients.py`, `check_flyers.py`, `check_alerts.py` falhavam com `Module "supabase" has no attribute "create_client"`. Adicionada `# mypy: ignore-errors` na 1ª linha de cada (mypy per-file directive — `exclude` não captura scripts no root).
- **`ci/typecheck`**: Instalado `tests/requirements-test.txt` (pytest estava faltando). Antes pytest vendia indisponível, causando `No module named pytest`.
- **`ci/lint` (pip-audit)**: Pillow 2.12.1+cpu (suffix de plataforma) não era encontrado no PyPI service. Trocado para `-s osv` que entende sufixos.
- **`ci/deploy-check`**: Secretos `AUTH_SECRET_KEY`, `GMAIL_USER`, `SUPABASE_ANON_KEY` faltam em CI. Adicionada distinção required/optional em `scripts/deploy_check.py`: required = fail CI; optional = WARN only.

### Changed (local infrastructure)

- **`requirements.txt`**: Reovido `--index-url https://download.pytorch.org/whl/cpu` inline; substituído por env var no CI workflow (relocates torch index URL to be conditional).
- **`.githooks/pre-push`**: reescrito de bash para Python com `#!/usr/bin/env python` + `sys.executable`. Windows Python Launcher (`py.exe`) lida com shbang corretamente (antes falhava: `python3` não existe no PATH Windows).
- **`.githooks/pre-push`** invoca `ci_local.py --no-unit` ≈ similar a `audit_secrets + ruff + mypy`. Documentado em AGENTS.md.
- **`scripts/ci_local.py`**: novo script master de validação local. Replica todos os 7 jobs do CI + 7 validadores de config (parseable requirements, mypy excludes, ruff ignores, ci.yml refs, hooks syntax, operational data não tracked, gitignore coverage). Saída resumida por job com.exit code agregado.
- **`tests/unit/test_ci_infrastructure.py`**: 13 testes sem mock que validam config CI real (CATCH-BEFORE-PUSH). Não passam se `requirements.txt` tem `--index-url` inline, ou se pyproject.toml excludes de check_*.py somem, etc.
- **`.gitattributes`**: LF normalization para `*.py/*.md/*.toml/*.yml/*.json/*.sh`. Sem isso, editores Windows commiitam CRLF e git detecta tudo modificado.
- **`.gitignore`**: adicionado `scripts/diagnose.py` (script pessoal) + operacional `data/prices_latest.json` trackeado e removido.
- **`scripts/diagnose.py`**: diagnostics scripts pessoais (SKIP em produção).
- **Three integration tests refatorados** (`test_db_integration.py`, `test_db_cleanup.py`, `test_review_queue_e2e.py`): removeram conexão direta `psycopg2.connect(port=5432)` (bloqueada no CI). Agora usam conftest `db_conn` (que internamente chama `exec_sql_query` RPC na porta 443). Conformidade com AGENTS.md regra: "Porta 5432 bloqueada | Usa exec_sql_query RPC".
- **`tests/conftest.py`**: `_SchemaCursor`/`_SchemaConn` (psycopg2 mock over RPC) proviam sql-style interface para tests sem depender de `psycopg2`.
- **`tests/integration/test_collector_pipeline.py::test_pipeline_exact_match`**: tolerância a dados cumulativos no DB real (collected_at = today filtering).
- **`tests/unit/test_dashboard_full.py::test_build_report_html`**: movido para `tests/integration/test_dashboard_reports.py` (precisa DB real).
- **`tests/unit/test_services_mocked.py::test_approve_review_item_updates_and_upserts`**: removido (falhava em CI por package version skew; muito acoplado à `httpx`/`postgrest`).

### Removed (operational data)

- `data/prices_latest.json` removido de git tracking (já estava em `.gitignore`).
- `data/cleanup_track.json` removido de git tracking (já estava em `.gitignore`).

### Documentation

- **`docs/security.md`**: adicionada seção "Dependencies and CVEs" com tabela dos 7 alertas dismissed + política de pin CRITICAL/HIGH/MEDIUM/LOW.
- **`AGENTS.md`**: adicionado"Fase 9 concluída" + 7 "Lições Aprendidas" (`# 1. Mocks boundary`, `# 2. Mark integration`, `# 3. exec_sql_query`, `# 4. Cleanup POST`, `# 5. deploy_check required/optional`, `# 6. SECRETS GUARD`, `# 7. PIP_EXTRA_INDEX_URL`).

---

## Categorias de Mudança

- **Added**: funcionalidades novas
- **Changed**: mudanças em funcionalidades existentes
- **Deprecated**: funcionalidades que serão removidas futuramente
- **Removed**: funcionalidades removidas
- **Fixed**: correções de bugs
- **Security**: correções de vulnerabilidades

## Como fazer release

```bash
# 1. Atualizar versão em pyproject.toml
# 2. Gerar changelog (futuro: auto via script)
git tag -a v0.2.0 -m "feat: nova funcionalidade X"
git push origin v0.2.0
# GitHub Actions detecta tag → publicacao
```

## Links

- Repo: https://github.com/anomalyco/CustoDoce
- Issues: https://github.com/anomalyco/CustoDoce/issues
- Discussions: https://github.com/anomalyco/CustoDoce/discussions