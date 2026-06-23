# CustoDoce - Memória do Projeto

## Sobre
Projeto de busca e comparação de preços de ingredientes para confeitaria.
Foco na Baixada Santista (Santos, São Vicente, Praia Grande, Mongaguá, Itanhaém, Peruíbe)
e São Paulo Capital. Infraestrutura 100% gratuita.

## Stack
- **DB/API**: Supabase (PostgreSQL) - 500MB free
- **Scrapers**: GitHub Actions (Python, 2.000 min/mês)
- **Dashboard**: Streamlit Cloud (Python, 1 app privado grátis)
- **Bot**: Telegram (python-telegram-bot)
- **Email**: Gmail SMTP (500 e-mails/dia)
- **Total Free Tier**: R$ 0,00

## Arquitetura

```mermaid
graph LR
    GH[GitHub Actions<br/>Cron 2x/dia] -->|Scrape + Normalize| SU[Supabase PostgreSQL]
    ST[Streamlit Dashboard] -->|Query| SU
    TG[Telegram Bot] -->|Dispatch| GH
    SU -->|Email Report| GM[Gmail SMTP]
```

## Estrutura de Diretórios

```
CustoDoce/
├── .github/workflows/
│   ├── scrape.yml                   # Coleta automática (cron + deploy)
│   └── ci.yml                       # CI: ruff + bandit + pytest + pip-audit
├── config/
│   ├── ingredients.yaml             # 18 ingredientes canônicos + aliases + search_terms
│   ├── stores.yaml                  # 50 lojas (Tier 1-4)
│   ├── features.yaml                # Flags declarativas liga/desliga
│   └── schema_prices.json           # Contrato de dados
├── scrapers/
│   ├── base_flyer.py                # ABC: download PDF + ETag cache + OCR fallback
│   ├── base_web_scraper.py          # ABC: httpx.Client + context manager + rate limit
│   ├── flyer_scraper.py             # Scraper genérico para PDFs (substitui 8 subclasses)
│   ├── flyer_parser.py              # Parser genérico de linhas de PDF
│   ├── vtex_scraper.py              # Scraper VTEX API (herda BaseWebScraper)
│   ├── website_scraper.py           # Scraper HTML (herda BaseWebScraper)
│   ├── carrefour_scraper.py         # Scraper Carrefour (herda BaseWebScraper)
│   ├── tenda_api_scraper.py         # API Tenda (herda BaseWebScraper)
│   ├── roldao_api_scraper.py        # API Roldão (herda BaseWebScraper)
│   ├── max_api_scraper.py           # API Max (herda BaseWebScraper)
│   ├── aggregator_scraper.py        # Agregadores SSR (Tiendeo, Guiato)
│   ├── playwright_scraper.py        # Agregadores JS (Playwright)
│   ├── playwright_price_scraper.py  # Scraper e-commerce SPA (Playwright)
│   ├── ocr.py                       # OCR fallback (Tesseract)
│   ├── unit_extractor.py            # Extrator centralizado de unidade
│   ├── extra_flyer_scraper.py       # Extra Folheteria (HTTP, OCR pre-extraido)
│   └── pao_flyer_scraper.py         # Pão de Açúcar Fresh (herda de ExtraFlyerScraper)
├── parsers/
│   ├── normalizer.py                # Extrai unidade → R$/kg + R$/un
│   ├── matcher.py                   # token_set_ratio ≥80% (RapidFuzz)
│   └── brand_extractor.py           # Extrai marca do texto do produto via YAML
├── services/
│   ├── supabase_client.py           # Singleton conexão
│   ├── price_service.py             # CRUD + busca + cleanup_old_prices/logs
│   ├── flyer_service.py             # CRUD flyers + cleanup_old_flyers
│   ├── email_service.py             # SMTP genérico (SMTP_* ou GMAIL_* fallback)
│   ├── telegram_service.py          # Telegram Bot API
│   ├── config.py                    # Config loader (cache + reload)
│   ├── config_db.py                 # DB-backed config (ingredients, stores, schedules, etc.)
│   ├── auth.py                      # PBKDF2 + JWT + TOTP
│   └── rate_limiter.py              # SQLite rate limit
├── telegram_bot/
│   └── handlers.py                  # /preco, /lista, /status
├── admin/
│   └── app.py                       # Streamlit dashboard (18 abas)
├── dashboard/
│   ├── login_page.py                # Auth + 2FA
│   └── components/
│       ├── ui.py                    # CSS + componentes reutilizáveis
│       └── layout.py                # Sidebar com navegação (18 páginas)
├── supabase/
│   ├── seed.sql                     # Tabelas + índices + RLS + triggers
│   ├── consolidated_migration.sql   # Migração consolidada (574 linhas)
│   └── 002_add_brand_column.sql     # Adiciona coluna brand nas tabelas
├── scripts/
│   ├── seed_prices.py               # Gera dados sintéticos (--dry-run/--execute/--json)
│   ├── deploy_database.py           # Migração SQL (--dry-run/--execute/--output)
│   ├── send_daily_report.py         # Relatório diário por email
│   └── deploy_check.py              # Health check pré-deploy
├── tests/
│   ├── test_dashboard_full.py       # 85 testes unitários
│   ├── test_services_mocked.py      # 75 testes com mocks
│   └── README.md                    # Plano de testes
├── main.py                          # Orquestrador: collect + cleanup loop
├── pyproject.toml                   # Ruff config (line-length=120, ignore E501)
├── requirements.txt                 # Dependências runtime
├── requirements-dev.txt             # Ferramentas de qualidade
├── packages.txt                     # System deps (tesseract-ocr, poppler-utils)
└── data/
    └── prices_latest.json           # Snapshot da última coleta
```

## Tiers de Lojas

| Tier | Tipo | Frequência | Como coleta |
|------|------|------------|-------------|
| 1 | PDF Direto (9 redes atacadistas) | Semanal (quarta/quinta) | Automatizado - pdfplumber |
| 2a | E-commerce SP (VTEX API) | Diária | Automatizado - requests API |
| 2b | Atacado Físico SP (Manos, Jabaquara etc.) | Mensal | Manual - visita + planilha |
| 3 | Agregadores (Tiendeo, Guiato) | Fallback | Automatizado - if tier 1/2 fail |
| 4 | Manual (WhatsApp, visita local) | Sob demanda | Planilha .xlsx |

## Ingredientes Monitorados (18)
1. Leite Condensado Integral (lacteos)
2. Creme de Leite 20% Gordura (lacteos)
3. Chocolate em Pó 50% Cacau (chocolates)
4. Leite Ninho Integral (lacteos)
5. Granulado Melken Ao Leite (confeitos)
6. Granulado Melken Branco (confeitos)
7. Granulado Melken Meio Amargo (confeitos)
8. Nutella (pastas)
9. Coloretti Granulado Colorido (confeitos)
10. Coco Ralado Grosso sem Açúcar (secos)
11. Chocolate Nobre Blend Harald (chocolates)
12. Açúcar Mascavo (acucares)
13. Açúcar de Confeiteiro (acucares)
14. Chocolate em Pó 70% Cacau (chocolates)
15. Farinha de Trigo (farinhas)
16. Micro Ball (confeitos)
17. Top Confete Morango (confeitos)
18. Gotas de Chocolate Branco (chocolates)

## Fluxo de Coleta (GitHub Actions)

```
1. Checkout repo
2. sudo apt-get tesseract-ocr (OCR fallback)
3. pip install -r requirements.txt
4. Cache MD5 de PDFs
5. main.py:
   a. Para cada loja Tier 1:
      - Se quarta/quinta:
        - build_url(week)
        - HEAD request (check ETag)
        - Se mudou: download PDF
        - MD5 check (cache)
        - Se igual → skip
        - pdfplumber extract text
        - Se vazio → OCR fallback (Tesseract)
        - flyer_parser → linhas produto + preço + unidade
        - process_price_match():
          - Matcher ≥80% → upsert_price()
          - Matcher 30-80% → insert_review_item(sugestões)
   b. Para cada loja Tier 2a (VTEX):
      - GET api/catalog_system/pub/products/search?ft=
      - Parse JSON VTEX → raw products
      - process_price_match() (mesmo fluxo acima)
   c. Para cada loja Tier 3 (Website):
      - GET {base_url}/busca?q=
      - selectolax → CSS selectors → raw products
      - process_price_match() (mesmo fluxo acima)
6. git commit data/prices_latest.json
7. Se 1º do mês: Release GitHub com snapshot mensal (prices_latest.json.gz)
8. Sempre: send_daily_report.py (email com top 5 preços por ingrediente)
```

## Matcher (parsers/matcher.py)

1. **Exact match**: canonical name in product text (case-insensitive)
2. **Alias exact**: each alias checked via `in` operator
3. **Word subset**: all canonical words found in product text
4. **Fuzzy fallback**: RapidFuzz `fuzz.token_set_ratio(product, canonical/alias)` threshold 80%
5. **Confidence Score**: 1.0 (exact), 0.8-1.0 (fuzzy ≥80%), <0.8 (review queue)
6. **Review Queue**: items with confidence <80% go to `review_queue` table

## Normalizer (parsers/normalizer.py)

```python
# Extrai do texto bruto: qty, unit_kg, total_kg
"cx 12x395g"       → qty=12, unit_kg=0.395, total_kg=4.74
"2kg"              → qty=1,  unit_kg=2.0,   total_kg=2.0
"500g"             → qty=1,  unit_kg=0.5,   total_kg=0.5
"cx 24x200g"       → qty=24, unit_kg=0.2,   total_kg=4.8
"12un 395g"        → qty=12, unit_kg=0.395, total_kg=4.74
"lata 1kg"         → qty=1,  unit_kg=1.0,   total_kg=1.0

# Preço normalizado:
price_per_kg = raw_price / total_kg
price_per_un = raw_price / qty
```

## Tratamento de Checagem e Validação de PDF

```python
# Em: scrapers/base_flyer.py
# Sequência:
# 1. generate URL from template: url_pattern.format(week=week, city=city)
# 2. httpx HEAD request (check ETag / Content-Length)
# 3. If modified: GET full PDF
# 4. compute MD5(content)
# 5. compare with cached MD5 (data/cache/{store}_md5.txt)
# 6. if same → skip (no changes)
# 7. if different → pdfplumber → extract text
# 8. update cache file
```

## Tratamento de Erros

| Erro | Ação |
|------|------|
| PDF não encontrado (404) | Loga aviso, pula loja |
| Timeout no download | Retry 2x, depois pula |
| ETag não mudou | Pula (cache hit) |
| pdfplumber vazio | Pula (PDF rasterizado - OCR fallback) |
| Matcher <80% | Vai para review_queue |
| Supabase offline | Salva em prices_latest.json local como fallback |
| Email falha | Loga erro, não bloqueia pipeline |

## Comandos Relevantes

```bash
# Testar um scraper manualmente
python -c "from scrapers.base_flyer import BaseFlyerScraper; s = BaseFlyerScraper({'name':'Assaí','url_pattern':'...'}); print(s.run())"

# Testar normalizer
python -c "from parsers.normalizer import normalize_price; print(normalize_price(42.90, 'cx 12x395g'))"

# Testar matcher
python -c "from parsers.matcher import match_ingredient; ing = [{'canonical':'Leite Condensado','aliases':[]}]; print(match_ingredient('Leite Condensado Moça 12un', ing))"

# Validar schema
python -c "import json, jsonschema; s=json.load(open('config/schema_prices.json')); jsonschema.validate({'ingredient_id':'x','store_id':'y','raw_price':1.0,'raw_product':'test','raw_unit':'un','collected_at':'2025-01-01','source':'manual'}, s)"
```

## Regras de Execução

1. **SEMPRE apresentar um plano antes de executar.** Conter: diagnóstico, correção proposta, e verificação. O usuário decide se quer que eu execute ou que outro agente execute.

2. **NUNCA fazer commit sem autorização explícita do usuário.** Mesmo que a correção esteja pronta e testada, esperar ordem.

3. **Ao pedir deploy, sempre pedir autorização.** Nunca deployar por conta própria.

4. **Após completar uma tarefa, apresentar resumo e esperar instrução.** Não assumir que devo seguir para a próxima coisa automaticamente.

## Regras de Responsividade

- **TODO componente deve ser responsivo**: celular (320px+), tablet (768px+), desktop (1024px+)
- **KPIs**: flex grid 2x2 no mobile, 4x1 no desktop
- **Tabelas**: `overflow-x: auto` + `min-width: 600px` — **nunca esconder colunas**
- **Grids**: CSS `grid-template-columns` com `repeat(auto-fill, minmax(...))` + media queries
- **Sempre validar** visualmente em múltiplos viewports antes de dar como pronto

## Infraestrutura de Testes

### Ferramentas
- `ruff` — lint (zero erros, config `pyproject.toml`)
- `mypy` — type hints (pendente)
- `bandit` — segurança (zero issues)
- `pip-audit` — CVEs (zero vulnerabilidades)
- `radon` — complexidade (média B)
- `pytest` — 230 testes (dashboard: 85, services: 145)
- `flake8` / `vulture` — código morto (opcional)

### Checklist por Fase
```
ruff check . && bandit -r admin/ dashboard/ services/ -x tests/ && pip-audit && python -m pytest tests/ -v
```

### Arquivos
- `tests/README.md` — plano de testes completo
- `requirements-dev.txt` — ferramentas de qualidade
- `tests/test_dashboard_full.py` — 85 testes unitários
- `tests/test_services_mocked.py` — 75 testes com mocks

## Fase 4 — CRUD Console (concluida)

| O que foi feito | Resultado |
|----------------|-----------|
| `tab_visao_geral` refatorada | E(38) → A(2) + 6 sub-funcoes |
| `tab_lojas` com filtros, busca, editor YAML | ✅ |
| `tab_ingredientes` com abas + testadores | ✅ |
| `_test_normalizer()` + `_test_matcher()` | ✅ |
| `generate_secret_key()` em auth.py | ✅ |
| Bug `is_limited` corrigido no rate_limiter | ✅ |
| 49 testes, ruff, bandit, pip-audit | ✅ Todos limpos |

## Fase 5 — Control & Reports (concluida)

| O que foi feito | Resultado |
|----------------|-----------|
| `tab_relatorios` — builder HTML com preview + envio | ✅ |
| `tab_relatorios` — abas: Relatorio, Testar SMTP, Testar Telegram | ✅ |
| `_test_smtp()` — testa conexao Gmail SMTP | ✅ |
| `_test_telegram()` — testa envio via Telegram Bot API | ✅ |
| `_render_schedule_info()` — exibe crons do scrape.yml | ✅ |
| `tab_scrapers` melhorada com schedule + logs | ✅ |
| 55 testes, ruff, bandit, pip-audit | ✅ Todos limpos |

## Fase 6 — System Config & Diagnostics (concluida)

| O que foi feito | Resultado |
|----------------|-----------|
| `tab_config` — secrets editor inline com edicao + salvar `.env` | ✅ |
| `tab_config` — variaveis agrupadas por categoria (5 grupos, 13 vars) | ✅ |
| `_mask_val()` — mascaramento padrao de secrets | ✅ |
| `tab_diagnostico` — testes individuais por componente com timing | ✅ |
| `tab_diagnostico` — testadores SMTP e Telegram inline | ✅ |
| `_render_schedule_info` — modo edicao de cron expressions | ✅ |
| Botao "Executar Todos" + "Limpar Resultados" | ✅ |
| 62 testes, ruff, bandit, pip-audit | ✅ Todos limpos |

## Fase 7 — Polish, Config Declarativo & Deploy (concluida)

| O que foi feito | Resultado |
|----------------|-----------|
| `config/features.yaml` — flags declarativas liga/desliga | ✅ |
| `services/config.py` com `get()` + cache + `reload()` | ✅ |
| Config guards no dashboard (telegram/email/alerts/export) | ✅ |
| `:focus-visible` rings CSS + `aria-label` sidebar | ✅ |
| Export CSV com `st.download_button` em Precos/Historico | ✅ |
| `scripts/deploy_check.py` — testa Supabase/Gmail/Telegram | ✅ |
| 70 testes, ruff, bandit, pip-audit | ✅ Todos limpos |

## Fase 8 — Dedup, Cleanup & Segurança (concluida)

| O que foi feito | Resultado |
|----------------|-----------|
| `upsert_price()` com `collected_at` truncado pra data (UNIQUE por dia) | ✅ |
| `insert_review_item()` dedup por `(store_name, raw_product)` — qualquer status | ✅ |
| `cleanup_old_prices(90)` — deleta prices + price_history > 90 dias | ✅ |
| `cleanup_old_logs(30)` — deleta scraping_logs > 30 dias | ✅ |
| `cleanup_old_flyers(60)` — deleta flyers com OCR failed + >60 dias | ✅ |
| Loop de cleanup no `main.py` (3 funções sequenciais) | ✅ |
| XSS sanitization `_sanitize()` — html.escape em todo unsafe_allow_html | ✅ |
| Senha hardcoded removida — `os.environ.get("ADMIN_PASSWORD")` + fallback | ✅ |
| HTML injection fix em `email_service.py` — _html.escape() | ✅ |
| `consolidated_migration.sql` — 574 linhas, todas as tabelas + funções | ✅ |
| **Adicionada constraint UNIQUE (ingredient_id, store_id, collected_at) em prices e price_history** | ✅ |
| **Correção da tabela scrape_frequencies: store_id TEXT REFERENCES stores(id)** | ✅ |
| 127 testes, ruff, bandit, pip-audit | ✅ Todos limpos |

## Fase 9 — Dashboard Insights (concluida)

| O que foi feito | Resultado |
|----------------|-----------|
| `tab_fontes` — Cobertura por Ingrediente + Promoções Ativas + Ranking Fontes | ✅ |
| `tab_ranking` — Gráfico linha/área/barras + ranking atual + estatísticas | ✅ |
| `tab_insights` — Heatmap (px.imshow) + Outliers (desvio padrão) + Melhores Ofertas | ✅ |
| `packages.txt` — tesseract-ocr + poppler-utils para Streamlit Cloud | ✅ |
| `ci.yml` — ruff + bandit + pytest + pip-audit em cada push/PR | ✅ |
| `seed_prices.py` — gera 4128 preços sintéticos (11 ing × 20 lojas × 91 dias) | ✅ |
| 17 páginas no dashboard sidebar (18 na Fase 13) | ✅ |
| 127 testes, ruff, bandit, pip-audit | ✅ Todos limpos |

## Fase 10 — Brand Extraction, Email/TG UX & Ruff Config (concluida)

| O que foi feito | Resultado |
|----------------|-----------|
| `config/ingredients.yaml` — campo `brands` adicionado a todos 11 ingredientes | ✅ |
| `parsers/brand_extractor.py` — `extract_brand()` + `extract_brand_from_all()` | ✅ |
| `scrapers/vtex_scraper.py` — lê `brand` da API + fallback `extract_brand()` | ✅ |
| `main.py` — `brand` propagado via `build_product_entry()` / `process_price_match()` | ✅ |
| `supabase/002_add_brand_column.sql` — coluna `brand` em prices/price_history/review_queue | ✅ |
| `services/price_service.py` — `brand` incluído no upsert de prices e review_queue | ✅ |
| `admin/app.py` — coluna "Marca" exibida em Preços, Histórico, Revisão, Promoções, Ranking, Ofertas | ✅ |
| Email templates rewrite — responsivo, logo CID, laranja+rosa, preheader, tagline, "Cotação de Preços" | ✅ |
| SMTP migrado de Outlook → Gmail (custodoce.alertas@gmail.com) | ✅ |
| Telegram template — mensagem consolidada com medals 🥇🥈🥉 | ✅ |
| UX audit — 27 issues corrigidas + docs/ux_audit.md | ✅ |
| `pyproject.toml` — Ruff config (`line-length=120`, `ignore=["E501"]`) + per-file-ignores `"admin/app.py" = ["E402"]` | ✅ |
| `scripts/archive/` — 6 fixes E741 + E722 | ✅ |
| 160 testes, ruff clean, bandit/pip-audit | ✅ Todos limpos |

## Fase 11 — Correção de Constraints & Migration (concluida)

| O que foi feito | Resultado |
|----------------|-----------|
| `_split_sql_statements()` — split SQL respeitando blocos `$$` (DO blocks) | ✅ |
| `deploy_database.py` — adicionado PHASE 7 com constraints UNIQUE 3-colunas | ✅ |
| `deploy_database.py` — adicionado PHASE 8 com scrape_frequencies corrigida | ✅ |
| `consolidated_migration.sql` — atualizado com PHASE 7 + 8 | ✅ |
| Constraint `UNIQUE (ingredient_id, store_id, collected_at)` em prices | ✅ |
| Constraint `UNIQUE (ingredient_id, store_id, collected_at)` em price_history | ✅ |
| Tabela `scrape_frequencies` com `store_id TEXT REFERENCES stores(id)` | ✅ |
| Migração executada: 124 OK, 34 WARN (todos inofensivos) | ✅ |
| Tratamento de erro 42P10 no dashboard com instrução SQL | ✅ |

## Fase 12 — Self-Learning Review Queue & Fixes (concluida)

| O que foi feito | Resultado |
|----------------|-----------|
| `search_prices()` — ordenação client-side para price_per_kg e price_per_un | ✅ |
| `search_prices()` — condicional `.order()` só para colunas diretas do DB | ✅ |
| `add_alias_to_ingredient()` — novo alias é adicionado ao ingrediente no DB | ✅ |
| `approve_review_item()` — aprovação adiciona raw_product como alias automaticamente | ✅ |
| `tab_revisao()` — explicação "Revisão necessária: confiança inferior a 80%" | ✅ |
| Bug `get_ingredient_by_id` corrigido para `get_ingredient_by_name` | ✅ |
| README.md — Fase 11 adicionada ao roadmap | ✅ |
| AGENTS.md — Fases 11 e 12 adicionadas ao Status | ✅ |

## Fase 13 — UX Audit Fixes + Calculadora de Receita (concluida)

| O que foi feito | Resultado |
|----------------|-----------|
| `docs/ux_audit.md` — 27 issues documentadas (6 críticas, 9 high, 8 medium, 4 low) | ✅ |
| UX fixes: bare excepts eliminados, spinners adicionados, dataframes com fallback, KPIs responsivos | ✅ |
| UX fixes: timezone padronizado, botões com confirmação, acessibilidade (tabindex, aria-label) | ✅ |
| `tab_calculadora()` — aba com modo Simples/Completo, auto-fill do menor preço do DB | ✅ |
| Modo Completo: top 3 lojas por ingrediente, 3 cenários de margem, salvar receita no Supabase | ✅ |
| `get_cheapest_prices()` — função no price_service que retorna top N preços mais baratos | ✅ |
| `recipes` + `recipe_items` — tabelas no Supabase (PHASE 9 da migration) | ✅ |
| Telegram inline: envio do resumo da receita via bot | ✅ |
| `supabase/consolidated_migration.sql` — PHASE 9 adicionada | ✅ |
| `dashboard/components/ui.py` — CSS do calculator (result cards, scenarios, ingredient rows) | ✅ |
| 16 páginas no dashboard sidebar | ✅ |
| 168 testes (85 dashboard + 80 services + 3 novos), ruff, bandit, pip-audit | ✅ Todos limpos |

## Fase 14e — Tab Consolidation (concluida)

| O que foi feito | Resultado |
|----------------|-----------|
| `tab_agendamentos()` movido para subtab dentro de `tab_scrapers()` | ✅ |
| `tab_frequencias()` movido para campos dentro do formulário de `tab_lojas()` | ✅ |
| Testadores SMTP/Telegram removidos de `tab_relatorios()` (mantidos em `tab_config` + `tab_diagnostico`) | ✅ |
| Bug `client if 'client' in dir()` corrigido (inicialização explícita) | ✅ |
| Bug `st.number_input(value=None)` eliminado (merge evitou o código quebrado) | ✅ |
| Sidebar reduzida de 18 para 16 abas | ✅ |
| 230 testes, ruff, bandit, pip-audit | ✅ Todos limpos |

## Fase 14f — Regression Bugfixes (concluida)

| O que foi feito | Resultado |
|----------------|-----------|
| `open()` sem `encoding='utf-8'` — corrigido em **9 arquivos** (main.py, admin/app.py x3, deploy_check.py, send_daily_report.py, setup_github_secrets.py, config.py, handlers.py) | ✅ |
| Price regex sem `\s*` antes de vírgula — corrigido em **4 scrapers** (carrefour_scraper.py, flyer_parser.py, website_scraper.py, playwright_price_scraper.py) | ✅ |
| `datetime.now()` sem timezone — corrigido em **5 arquivos** (main.py, price_service.py, flyer_service.py, aggregator_scraper.py, seed_prices.py) | ✅ |
| 230 testes, ruff (0 new), bandit (0), pip-audit (0) | ✅ Todos limpos |

## Fase 15 — Review Queue Enhanced (concluida)

| O que foi feito | Resultado |
|----------------|-----------|
| Schema: coluna `match_type TEXT DEFAULT ''` em `review_queue` (PHASE 9 migration) | ✅ |
| `main.py`: `match_reason` detalhado com tipo de match, score, candidato, termo match, palavras não matcheadas | ✅ |
| `main.py`: review item inclui `match_type`, `top3` (top 3 candidatos com scores) | ✅ |
| `main.py`: flyers passam `source_url` do prod ou flyer dict | ✅ |
| `services/price_service.py`: `insert_review_item()` inclui `match_type` | ✅ |
| `admin/app.py`: layout 2 colunas — imagem/dados lado a lado (não mais expander) | ✅ |
| `admin/app.py`: barra de confiança visual (`st.progress`) | ✅ |
| `admin/app.py`: badge de match_type colorido (verde=exato, amarelo=fuzzy, azul=word_subset) | ✅ |
| `admin/app.py`: seção "Top 3 Candidatos" com scores individuais + progress bars | ✅ |
| `admin/app.py`: diagnóstico detalhado com tipo, score, candidato, termo, palavras não matcheadas | ✅ |
| `scripts/deploy_database.py`: PHASE 9 adicionada (match_type + image_url + source_url + match_reason) | ✅ |
| `scripts/deploy_database.py`: PHASE 9 — colunas `image_url`, `source_url`, `match_reason` (faltavam desde Fase 14c) | ✅ |
| `scripts/check_schema_diff.py`: review_queue schema atualizado | ✅ |
| Migration executada no Supabase: PHASE 7 (UNIQUE constraint) + PHASE 9 (4 colunas) | ✅ |
| 230 testes, ruff 0, bandit 0 | ✅ Todos limpos |

## Fase 15b — DB Gaps & Refactor (concluida)

| O que foi feito | Resultado |
|----------------|-----------|
| `reject_review_item()` — corrigido retorno `[]`→`{}` (quebrava `dict.get()`) | ✅ |
| `upsert_price()` — removido dead code `valid_until` (linha 26 sobrescrita na 28) | ✅ |
| `get_review_queue()` — adicionado `.limit(500)` (travamento com 10k+ itens) | ✅ |
| Export CSV — criado `_export_csv_button()` helper, refatorado 8 locais (**-96 linhas**) | ✅ |
| `_cached_get_all_current_prices()` — criado com ttl=60s, substitui 6 chamadas diretas | ✅ |
| `approve_review_item()` — `store_id` agora busca real via `get_store_by_name()` (não mais fabricado) | ✅ |
| 5 índices de performance — PHASE 10: `idx_prices_ing_collected`, `idx_history_ing_collected`, `idx_review_collected`, `idx_stores_name`, `idx_logs_store_started` | ✅ |
| Migration no Supabase: PHASE 10 executada + `consolidated_migration.sql` atualizado | ✅ |
| 230 testes, ruff 0, bandit 0 | ✅ |

## Status das Fases

- **Fase 1** ✅ Estrutura base (pastas, parsers, services, schema, base_flyer)
- **Fase 2** ✅ Scrapers VTEX — `vtex_scraper.py` (Rizzo, Amendolate, Loja Sto Antônio + demais VTEX)
- **Fase 3a** ✅ Scrapers site — `website_scraper.py` (Cacau Center, Confeitos & Cia, Padeirão + demais)
- **Fase 3b** ✅ Template planilha visitas SP (`scripts/generate_visit_template.py`) + importador (`scripts/import_visit_spreadsheet.py`)
- **Fase 3c** ✅ Dashboard Flyers & History — grid responsivo de flyers, detale com OCR, gráficos históricos com R$/kg, heatmap de cobertura, KPIs na Home
- **Fase 4** ✅ Fila de revisão no dashboard — `process_price_match()` roteia <80% para `review_queue`; dashboard permite aprovar/rejeitar com seleção de ingrediente
- **Fase 5** ✅ Control & Reports — `tab_relatorios` (builder HTML + preview + envio); `_test_smtp()` / `_test_telegram()`; agendamento exibido em `tab_scrapers`
- **Fase 6** ✅ System Config & Diagnostics — secrets editor `tab_config` (5 grupos, 13 vars, inline edit + save `.env`); `tab_diagnostico` com testes individuais + SMTP/Telegram inline; schedule manager com edição de crons
- **Fase 7** ✅ Polish & Deploy — `config/features.yaml` (flags declarativas liga/desliga); `services/config.py` com `get()` + cache + `reload()`; config guards no dashboard; `:focus-visible` rings CSS + `aria-label` sidebar; export CSV com `st.download_button`; `scripts/deploy_check.py`
- **Fase 8** ✅ Dedup & Cleanup — `collected_at` truncado pra data; review queue dedup sem filtro status; `cleanup_old_prices(90)` + `cleanup_old_logs(30)` + `cleanup_old_flyers(60)`; XSS sanitization; HTML injection fix; consolidated migration SQL
- **Fase 9** ✅ Dashboard Insights — `tab_fontes` (cobertura + promoções + ranking); `tab_ranking` (gráficos + estatísticas); `tab_insights` (heatmap + outliers + melhores ofertas); CI/CD (ci.yml + packages.txt); seed data (4128 preços sintéticos)
- **Fase 10** ✅ Brand Extraction — `brand_extractor.py`, coluna `brand` no DB, coluna "Marca" no dashboard; Email/TG UX overhaul; Ruff config (`pyproject.toml`)
- **Fase 11** ✅ Correção de Constraints — UNIQUE (ingredient_id, store_id, collected_at) em prices e price_history, correção scrape_frequencies (store_id TEXT), tratamento de erro 42P10
- **Fase 12** ✅ Self-Learning Review Queue — ordenação client-side, aliases automáticos ao aprovar, explicação na UI
- **Fase 13** ✅ UX Audit Fixes + Calculadora de Receita — 27 UX issues corrigidas, calculadora Simples/Completo com auto-fill, salvar receitas no Supabase, 168 testes
- **Fase 14a** ✅ Performance Optimization — `get_all_current_prices()` elimina 55+ N+1; 12 cached wrappers `@st.cache_data`; hoisting de queries duplicadas; `get_latest_prices()` limit 500→2000; `get_telegram_report()` 1 query em vez de 11
- **Fase 14b** ✅ Playwright Price Scraper + Health Check — `playwright_price_scraper.py` (SPA e-commerce); `_auto_disable_if_needed()` (3 falhas → desativa); `test_scraper_health()` no deploy_check; 7 novos ingredientes (18 total); 225 testes
- **Fase 14c** ✅ Review Queue Overhaul — threshold 30%→55% (elimina ~95% falsos positivos); colunas `image_url`, `source_url`, `match_reason`, `brand` na `review_queue`; `matcher.py` retorna `(ingredient, score, match_type, matched_term)`; `tab_revisao` exibe: motivo do match, expander com imagem do panfleto, botão link para página do produto; 227 testes
- **Fase 14d** ✅ Pão de Açúcar Fresh Scraper — `pao_flyer_scraper.py` herda de `ExtraFlyerScraper` com `BRAND=pao`, `CAMPAIGN_TYPE=fresh`; ExtraFlyerScraper refatorado: class-level attrs `BRAND` e `CAMPAIGN_TYPE`; store `"Pão de Açúcar Fresh"` (Tier 1, type `pao_flyer`); 101 produtos/roda em teste manual; 230 testes
- **Fase 14e** ✅ Tab Consolidation — `tab_agendamentos()` → subtab de `tab_scrapers()`; `tab_frequencias()` → campos no form `tab_lojas()`; testadores SMTP/Telegram removidos de `tab_relatorios()`; sidebar 18→16 abas; 230 testes
- **Fase 14f** ✅ Regression Bugfixes — `open()` encoding utf-8 (9 arquivos), price regex `\s*` (4 scrapers), `datetime.now(timezone.utc)` (5 arquivos); 230 testes; ruff/bandit/pip-audit limpos
- **Fase 15** ✅ Review Queue Enhanced — coluna `match_type`, `match_reason` detalhado (tipo, score, candidato, termo, palavras não matcheadas), top 3 com scores, UI 2 colunas com imagem sempre visível, badge de match type colorido, progress bar de confiança; 230 testes
- **Fase 15b** ✅ DB Gaps & Refactor — `reject_review_item()` retorna `{}`, dead code removido, `get_review_queue()` com `.limit(500)`, `_export_csv_button()` helper (**-96 linhas**), `_cached_get_all_current_prices()` substitui 6 chamadas, `store_id` real em vez de fabricado, 5 índices PHASE 10; 230 testes
