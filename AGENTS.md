# CustoDoce - Memória do Projeto

> **~370 linhas vivo.** Lições → `LESSONS.md`. Regras infra → `REGRAS.md`.

## Regras Mandatórias (Top 10)

1. **Schema contracts**: `config/agents_schema.yaml` define o que entra aqui. CI valida.
2. **Mocks na boundary, não na definição**: `@patch("onde.usado.import")`, não `@patch("onde.definido")`.
3. **Padrão de Testes**: Novo código = novos testes (`test_<modulo>.py`); testes com Supabase real devem usar `@pytest.mark.integration`.
4. **`exec_sql_query` RPC (porta 443), NUNCA `psycopg2`**: GH Actions bloqueia 5432.
5. **<55% vai pra review_queue**: `match_type`, `match_reason`, brand, top3 candidatos.
6. **Self-healing em todo scraper**: `record_failure/success()` obrigatório. `scraper_health.py`.
7. **`normalized` pode ser `true` (bool)** — SEMPRE proteger: `isinstance(raw, dict)` antes de `.get()`.
8. **Migration SQL nova → adicionar em `scripts/deploy_database.py::generate_consolidated()`**.
9. **`httpx` pinado `<1.0`** no `requirements.txt`.
10. **Paridade Total de Ambiente**: Python, deps (requirements.lock), runtime, OS e versões de ferramentas devem ser IDÊNTICOS entre local (Windows/WSL), CI (GitHub Actions) e Cloud (Streamlit). Qualquer divergência bloqueia merge — CI valida no alvo real. (Ver `REGRAS.md` §4)

## Sobre

Busca e comparação de preços de ingredientes para confeitaria. Foco na Baixada Santista e São Paulo Capital. Infraestrutura 100% gratuita.

## Stack

- DB/API: Supabase (PostgreSQL, 500MB free)
- Scrapers: GitHub Actions (Python, 2.000 min/mês)
- Dashboard: Streamlit Cloud (1 app privado)
- Bot: Telegram (python-telegram-bot)
- Email: Gmail SMTP (500 e-mails/dia)
- AI/ML: Sentence-Transformers (ONNX), Groq API, Scikit-learn (Isolation Forest)
- **Free Tier Total**: R$ 0,00

## Arquitetura

```mermaid
graph LR
    GH[GitHub Actions<br/>Cron 2x/dia] -->|Scrape + Normalize| SU[Supabase PostgreSQL]
    ST[Streamlit Dashboard] -->|Query| SU
    TG[Telegram Bot] -->|/preco /lista /status| SU
    TG -->|/scrape| GH
    SU -->|Email Report| GM[Gmail SMTP]
```

## Estrutura de Diretórios

```
CustoDoce/
├── .github/workflows/
│   ├── scrape.yml, ci.yml, e2e.yml, backup.yml, restore-test.yml
│   ├── deploy-staging.yml, on_demand_scrape.yml, ci-e2e-only.yml
│   ├── heal-scrapers.yml                             # Cron 15d auto-heal
│   └── skills-maintenance.yml                       # Cron mensal (dia 1, 9am UTC)
├── .githooks/
│   ├── pre-commit                                     # 5 camadas (secret, doc sync, size, watchdog, agents)
│   └── pre-push                                       # Python, 4 steps + agents_tool
├── config/
│   ├── ingredients.yaml, stores.yaml, features.yaml
│   ├── schema_prices.json, agents_schema.yaml         << NOVO
├── scrapers/          # base_flyer, vtex, playwright, flyer, parser, ocr, etc.
├── parsers/           # normalizer, matcher, brand_extractor, llm_cache, llm_strategies, llm_classifier
├── services/          # supabase_client, price_*, collector, email, telegram, alert, logger, otel, etc.
├── dashboard/         # login_page, components/ (ui, layout), pages/ (18 módulos)
├── telegram_bot/      # handlers.py
├── admin/app.py       # 107 linhas — importa 19 pages
├── supabase/          # seed.sql, consolidated_migration.sql, migrations 002-005
├── scripts/           # deploy, validate, sync, audit, seed, heal, sanity, send_report, skills_maintenance
├── tests/             # unit (518), schema (94), integration, design, e2e, real
├── data/prices_latest.json
├── pyproject.toml     # Ruff 120 chars, mypy 3.12, pytest config
├── requirements.txt   # httpx<1.0, supabase, streamlit, groq, torch, etc.
├── AGENTS.md          # ← este arquivo (vivo, ~370 linhas)
├── LESSONS.md         # 32 lições aprendidas
└── REGRAS.md          # Ambiente, hooks, comandos
```

## Tiers de Lojas

| Tier | Tipo | Frequência | Como coleta |
|------|------|------------|-------------|
| 1 | PDF Direto (9 redes atacadistas) | Semanal (qua/qui) | pdfplumber + OCR fallback |
| 2a | E-commerce SP (VTEX API) | Diária | requests API |
| 2b | Atacado Físico SP | Mensal | Manual (planilha) |
| 3 | Agregadores (Tiendeo, Guiato) | Fallback | Playwright / SSR |
| 4 | Manual (WhatsApp, visita) | Sob demanda | Planilha .xlsx |

## Ingredientes Monitorados (23)

[Leite Condensado, Creme de Leite, Chocolate 50%, Leite em Pó, Granulado Ao Leite, Granulado Branco, Granulado Meio Amargo, Creme de Avelã, Granulado Colorido, Coco Ralado, Chocolate Nobre Blend, Açúcar Mascavo, Açúcar Confeiteiro, Chocolate 70%, Farinha de Trigo, Micro Ball, Top Confete, Gotas Branco, Manteiga, Gotas Meio Amargo, Chocolate Barra, Fermento, Baunilha] — detalhes completos em `config/ingredients.yaml`.

## Fluxo de Coleta (GitHub Actions scrape.yml)

```
main.py → sync_store_fields() → para cada loja ativa:
  Tier 1 (PDF): build_url → HEAD (ETag) → download → MD5 cache → pdfplumber → OCR fallback
  Tier 2a (VTEX): GET api/products/search?ft= → parse JSON
  Tier 3 (site): GET /busca?q= → selectolax CSS selectors
  Todos → process_price_match():
    → match_ingredient() [exact → alias → word_subset → fuzzy RapidFuzz ≥80%]
    → se ≥80%: upsert_price_rpc()
    → se 55-79%: semantic_matcher blend (RapidFuzz 0.6 + embeddings 0.4)
    → se 65-80%: llm_classifier (Groq)
    → se <55%: review_queue
  Fim: enrich_prices() [Isolation Forest] → commit prices_latest.json → email report
  1º do mês: release GitHub com snapshot .json.gz
```

## Matcher (parsers/matcher.py)

1. **Exato**: canonical name no texto do produto
2. **Apelido exato**: cada alias com `in` operator
3. **Contido**: todas as palavras do canonical no produto
4. **Fuzzy**: RapidFuzz `fuzz.token_set_ratio(product, canonical/alias)` ≥80%
5. **Match types**: `exato` / `proximo_nome` / `proximo_apelido` / `contido`
6. **Confidence**: 1.0 (exato), 0.8-1.0 (fuzzy), <0.8 (review queue)
7. **Brand extraction**: 3 níveis (exato → substring regex → fuzzy palavra a palavra ≥80%)

## Normalizer (parsers/normalizer.py)

```
"cx 12x395g" → qty=12, unit_kg=0.395, total_kg=4.74
"2kg"        → qty=1,  unit_kg=2.0,   total_kg=2.0
"500g"       → qty=1,  unit_kg=0.5,   total_kg=0.5
"12un 395g"  → qty=12, unit_kg=0.395, total_kg=4.74
"lata 1kg"   → qty=1,  unit_kg=1.0,   total_kg=1.0

price_per_kg = raw_price / total_kg
price_per_un = raw_price / qty
```

## Tratamento de Erros

| Erro | Ação |
|------|------|
| PDF 404 | Loga aviso, pula loja |
| Timeout | Retry 2x, depois pula |
| ETag não mudou | Pula (cache hit) |
| pdfplumber vazio | OCR fallback (Tesseract) |
| Matcher <80% | Review queue |
| Supabase offline | Salva em prices_latest.json local |
| Email falha | Loga erro, não bloqueia pipeline |
| Porta 5432 bloqueada | `exec_sql_query` RPC (porta 443) |

## ⚠️ Regra Obrigatória: DB Sync

**Toda alteração em SQL/funções/triggers deve ser verificada na base real do Supabase via RPC (`exec_sql_query`, porta 443).** NUNCA `psycopg2` direto.

```bash
python scripts/deploy_database.py --execute
ruff check . && python -m pytest tests/unit/ tests/schema/ -q
```

## Comandos Relevantes

```bash
# Lint + type + test
ruff check . && python -m mypy . && python -m pytest tests/unit/ tests/schema/ -q

# Gestão do AGENTS.md
python scripts/agents_tool.py --check      # Valida schema
python scripts/agents_tool.py --full       # Validação completa
python scripts/agents_tool.py --status     # Estado atual
python scripts/agents_tool.py --add-rule   # Adicionar regra top 10
python scripts/agents_tool.py --add-lesson # Adicionar lição

# Schema / DB
python scripts/deploy_database.py --dry-run
python scripts/validate_db_schema.py

# Testes específicos
python -m pytest tests/unit/ tests/schema/ -q
python -m pytest tests/integration/ -q -x
```

## Status Atual

| Métrica | Valor |
|---------|-------|
| pytest (unit + schema) | 612 passing |
| pytest (integration) | 112 passing |
| pytest (real, slow) | 6 passing |
| AGENTS.md | 974→~370 linhas (Sprint 11 sanitization) |
| LESSONS.md | 32 lições movidas |
| REGRAS.md | Ambiente + hooks + comandos |
| CI lint/type/test | ✅ Todos verdes (Python 3.14) |
| E2E (cloud) | ⏳ Mensal (Playwright) |
| Python local (Windows) | 3.14.6 (`.venv314`) |
| Python CI (GitHub Actions) | 3.14 (`PYTHON_VERSION=3.14`) |
| Python WSL | 3.14 (`custodoce-314`) |
| Python Cloud (Streamlit) | 3.14 (pending UI update) |
| requirements.lock | 130+ packages, no hashes |
| OpenCode Skills | 33 installed (todas no projeto) |

## OpenCode Skills

**33 skills** em `.opencode/skills/`.

### Categorias

| Categoria | Skills | Propósito |
|-----------|--------|------------|
| **Vibe Coding** | project-context-primer, code-review, github, dependency-audit, knowledge-base-update, brainstorming, writing-plans, prompt-enhancer, architecture-review, test-driven-execution, documentation-sync, incident-response | Workflows produtivos |
| **CustoDoce Core** | web-scraper, price-normalizer, llm-integration, self-healing, brand-extractor | Domain-specific |
| **Streamlit UI** | streamlit, streamlit-theming, streamlit-components, streamlit-responsive, accessibility, design-md | Dashboard excellence |
| **Ops** | skills-maintenance | Manutenção |

### Manutenção

```bash
# Verificar status (mensal automático via skills-maintenance.yml)
python scripts/skills_maintenance.py --check

# Validar estrutura (a cada PR)
python scripts/skills_maintenance.py --validate

# Backup + Check + Validate (trimestral)
python scripts/skills_maintenance.py --full

# Listar todas
python scripts/skills_maintenance.py --list
```

### Cron

- **Mensal** (1º do mês, 6am SP / 9am UTC): `skills-maintenance.yml` executa `--check`
- **A cada PR**: CI valida estrutura das skills modificadas
- **Manual**: `workflow_dispatch` com modos `check | validate | full`

## Ambiente

**Python local OBRIGATÓRIO: `.venv314`** (PowerShell → `& .\.venv314\Scripts\Activate.ps1`).

O **`pre-push`** detecta `.venv314` automaticamente via `_resolve_python()` (ver `REGRAS.md` §Pre-push). Independente de como o git foi invocado, todo subprocesso do hook usa o Python do venv → **paridade total com CI/Cloud**. Fallback `sys.executable` é apenas aviso, não erro.

Para WSL: `custodoce-314` (Conda, Python 3.14). Detalhes em `REGRAS.md`.

## Documentação Relacionada

- `LESSONS.md` — 32 lições aprendidas (CI, mocks, schema, scrapers)
- `REGRAS.md` — Ambiente, hooks, comandos, arquitetura
- `docs/skills.md` — Skills OpenCode (globais + overlays locais)
- `docs/changelog.md` — Histórico por fase/sprint
- `config/agents_schema.yaml` — Schema deste arquivo
