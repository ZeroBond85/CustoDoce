# Changelog

Todos os cambios_notáveis deste projeto são documentados aqui.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere a [Semantic Versioning](https://semver.org/lang/pt-BR/).

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

## [unreleased]

### Fixed
- E2E tests now collect (renamed `e2e_*.py` → `test_e2e_*.py` in `tests/e2e/` to match `python_files = test_*.py`). Added 49 collected tests across dashboard + Playwright + flyer validation.
- Updated `.github/workflows/e2e.yml` and `scripts/generate_regression_report.py` references.

### Added
### Changed
### Deprecated
### Removed
### Security

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