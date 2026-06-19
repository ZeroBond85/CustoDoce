# CustoDoce - Buscador de Preços para Confeitaria

Sistema automatizado de busca e comparação de preços de ingredientes para confeitaria, focado na **Baixada Santista** (Santos, São Vicente, Praia Grande, Mongaguá, Itanhaém, Peruíbe) e **São Paulo Capital**. Infraestrutura 100% gratuita.

## Funcionalidades

- 🔍 **Busca automática 2x/dia** - Coleta preços de PDFs de atacados, APIs VTEX e sites
- 🏪 **17 abas no dashboard** - Visão geral, preços, histórico, flyers, revisão, fontes, ranking, insights, lojas, ingredientes, scrapers, relatórios, config, diagnóstico
- 🤖 **Telegram Bot** - `/preco <ingrediente>` → lista ordenada por R$/kg
- ⚙️ **Config declarativa** - Edite `config/features.yaml` para ligar/desligar funções sem alterar código
- 📊 **Export CSV** - Download de preços e histórico em CSV
- 📧 **Email + Telegram Testers** - Teste de conexão SMTP e Telegram inline no dashboard
- 🔬 **Diagnóstico automático** - Health check individual por componente com timing
- 📦 **Histórico em GitHub Releases** - Sem bloat no git

## Tech Stack

| Camada | Tecnologia | Free Tier |
|--------|------------|-----------|
| **Banco + API** | Supabase (PostgreSQL) | 500 MB |
| **Scrapers** | GitHub Actions | 2.000 min/mês |
| **Dashboard** | Streamlit Cloud | 1 app privado |
| **Telegram** | python-telegram-bot | Grátis |
| **Email** | Gmail SMTP | 500/dia |

## Pré-requisitos

- [ ] Conta [GitHub](https://github.com) (gratuita)
- [ ] Conta [Supabase](https://supabase.com) (gratuita)
- [ ] Conta [Streamlit Cloud](https://streamlit.io/cloud) (gratuita - login com GitHub)
- [ ] Conta [Gmail](https://gmail.com) (gratuita)
- [ ] Telegram instalado no celular

## Setup Passo a Passo

### 1. Criar Projeto Supabase

1. Acesse [supabase.com](https://supabase.com) e faça login com GitHub
2. Clique **"New Project"**
3. Preencha:
   - Name: `custodoce`
   - Database Password: **anote em local seguro**
   - Region: `South America (São Paulo)`
4. Aguarde (2-3 minutos)
5. Vá em **Settings → API** e copie:
   - `Project URL` → será `SUPABASE_URL`
   - `anon public` → será `SUPABASE_ANON_KEY`
   - `service_role secret` → será `SUPABASE_SERVICE_ROLE_KEY`

### 2. Rodar Schema do Banco

1. No Supabase, vá em **SQL Editor**
2. Abra `supabase/seed.sql` do projeto
3. Cole e execute (**Ctrl+Enter**)
4. Verifique: tabelas `prices`, `price_history`, `review_queue`, `scraping_logs`, `stores` criadas

### 3. Criar Bot no Telegram

1. Abra o Telegram e pesquise por **@BotFather**
2. Envie `/newbot`
3. Nome: `CustoDoce Preços` (ou qualquer nome)
4. Username: `CustoDoceBot` (ou similar - deve terminar com `bot`)
5. Copie o **token** (ex: `123456:ABC-DEF1234...`)
6. Envie `/setprivacy` → `Disable` (para o bot ver todas as mensagens)
7. Envie `/setdescription` → `Buscador de preços de ingredientes para confeitaria. Use /preco <ingrediente> para buscar.`
8. Envie `/setcommands`:
   ```
   preco <ingrediente> - Buscar preços do ingrediente
   lista - Listar todos os ingredientes
   status - Status do sistema
   ajuda - Ajuda
   ```

### 4. Obter CHAT_ID

1. Pesquise por **@userinfobot** no Telegram
2. Envie `/start`
3. Copie o número `Id` (ex: `123456789`) → será `TELEGRAM_CHAT_ID`

### 5. Configurar Gmail

1. Acesse [myaccount.google.com/security](https://myaccount.google.com/security)
2. Ative **"Verificação em duas etapas"** (obrigatório)
3. Vá em **"Senhas de app"**
4. Nome: `CustoDoce Bot`
5. Copie a senha de **16 caracteres** gerada → será `GMAIL_APP_PASSWORD`

### 6. Fazer Fork/Clone do Repositório

```bash
# No terminal:
git clone https://github.com/SEU_USUARIO/CustoDoce.git
cd CustoDoce
```

Ou crie o repositório manualmente e faça upload dos arquivos.

### 7. Adicionar Secrets no GitHub

1. No repositório, vá em **Settings → Secrets and variables → Actions**
2. Clique **"New repository secret"** e adicione cada um:

| Secret | Valor |
|--------|-------|
| `SUPABASE_URL` | `https://xxxx.supabase.co` |
| `SUPABASE_ANON_KEY` | `eyJxxxx` |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJxxxx` (service_role, não anon) |
| `TELEGRAM_TOKEN` | `123456:ABC-DEF1234` |
| `TELEGRAM_CHAT_ID` | `123456789` |
| `GMAIL_USER` | `seuemail@gmail.com` |
| `GMAIL_APP_PASSWORD` | `xxxx xxxx xxxx xxxx` |
| `ALERT_EMAIL_TO` | `seuemail@gmail.com` |
| `GH_PAT` | Token GitHub (Settings → Developer → PAT, escopo `repo`) |

### 8. Rodar o Workflow Manualmente

1. Vá em **Actions → CustoDoce - Coleta Diária de Preços**
2. Clique **"Run workflow"** (botão azul à direita)
3. Aguarde a execução (2-5 minutos)
4. Verifique os logs: deve mostrar conexão com Supabase e tentativas de download

### 9. Verificar Dados no Supabase

1. No Supabase, vá em **Table Editor**
2. Abra a tabela `prices`
3. Se a coleta funcionou, você verá linhas com `ingredient_id`, `raw_price`, `store_name`

### 10. Dar um ping no Bot do Telegram

1. Abra o Telegram
2. Pesquise pelo seu bot (username que você criou)
3. Envie `/start`
4. Envie `/status`
5. Envie `/preco leite condensado`

### 11. Deploy do Streamlit Dashboard

1. Acesse [share.streamlit.io](https://share.streamlit.io)
2. Faça login com GitHub
3. Clique **"New app"**
4. Selecione o repositório `CustoDoce`
5. Branch: `main`
6. Main file path: `admin/app.py`
7. Clique **"Deploy"**
8. Vá em **Settings → Secrets** e adicione:
   ```toml
   SUPABASE_URL = "https://xxxx.supabase.co"
   SUPABASE_ANON_KEY = "eyJxxxx"
   ADMIN_PASSWORD = "sua_senha_admin"
   ```
9. Acesse o dashboard em `https://custodoce.streamlit.app`

## Comandos do Telegram

```
/preco leite condensado    → Lista preços ordenados por R$/kg
/preco chocolate           → Busca chocolate
/preco nutella             → Busca nutella
/lista                     → Lista todos ingredientes
/status                    → Status do sistema
/ajuda                     → Ajuda completa
```

## Comandos do Dashboard (Streamlit)

| Aba | Função |
|-----|--------|
| **Visão Geral** | KPIs (preços/flyers), top 3 mini-cards, boxplot, heatmap cobertura, alertas variação |
| **Preços** | Busca por ingrediente, ordenação, top 3, gráfico barras, export CSV |
| **Histórico** | Gráficos linha/scatter R$/kg, cobertura por loja, export CSV |
| **Flyers** | Grid responsivo, filtros (status/source/período), detalhe com OCR |
| **Revisão** | Fila de itens <80% confiança (aprovar/rejeitar) |
| **Fontes & Ofertas** | Cobertura por ingrediente, promoções ativas, ranking de fontes |
| **Ranking** | Gráfico linha/área/barras, ranking atual, estatísticas do período |
| **Insights** | Heatmap preço×loja, outliers por desvio padrão, melhores ofertas |
| **Lojas** | CRUD via YAML inline, filtros tier, busca |
| **Ingredientes** | CRUD via YAML, testadores normalizer + matcher |
| **Scrapers** | Trigger manual GitHub Actions, schedule info + editor, logs |
| **Relatórios** | Builder HTML com preview + envio email, testers SMTP/Telegram |
| **Configuração** | Secrets editor inline (5 grupos, 13 vars), save .env, features YAML |
| **Diagnóstico** | Testes individuais por componente com timing, SMTP/Telegram inline |

## Estrutura do Projeto

```
CustoDoce/
├── .github/workflows/
│   ├── scrape.yml                   # Coleta automática (cron + deploy)
│   └── ci.yml                       # CI: ruff + bandit + pytest + pip-audit
├── config/
│   ├── ingredients.yaml             # 11 ingredientes + aliases + search_terms
│   ├── stores.yaml                  # 49 lojas (Tier 1-4)
│   ├── features.yaml                # Flags declarativas liga/desliga
│   └── schema_prices.json           # Validação dos dados
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
│   ├── ocr.py                       # OCR fallback (Tesseract)
│   └── unit_extractor.py            # Extrator centralizado de unidade
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
│   └── app.py                       # Streamlit dashboard (17 abas)
├── dashboard/
│   ├── login_page.py                # Auth + 2FA
│   └── components/
│       ├── ui.py                    # CSS + componentes reutilizáveis
│       └── layout.py                # Sidebar com navegação (17 páginas)
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

## Licenciamento de Lojas (Tiers)

| Tier | Tipo | Exemplos | Frequência |
|------|------|----------|------------|
| 1 | PDF Direto (Atacados) | Assaí, Atacadão, Spani, Mercadão | Semanal |
| 2a | E-commerce SP Capital | Rizzo, Amendolate, Loja Sto Antônio | Diária |
| 2b | Atacado Físico SP | Manos, Jabaquara, Marsil | Mensal (manual) |
| 3 | Agregadores | Tiendeo, Guiato | Fallback |
| 4 | Manual | Bolão Docemania, SAV Fratelli | Sob demanda |

## Roadmap

- [x] **Fase 1** — Estrutura base: scrapers PDF, parsers, Supabase, Telegram
- [x] **Fase 2** — Scrapers VTEX + site + OCR fallback
- [x] **Fase 3** — Dashboard Flyers & History + KPIs + heatmap
- [x] **Fase 4** — CRUD Console: lojas/ingredientes inline + testadores
- [x] **Fase 5** — Control & Reports: builder HTML, SMTP/Telegram testers
- [x] **Fase 6** — System Config & Diagnostics: secrets editor, health check
- [x] **Fase 7** — Polish & Deploy: config declarativa, acessibilidade, export CSV, deploy check
- [x] **Fase 8** — Dedup & Cleanup: collected_at truncado, review dedup, cleanup_old_prices/logs/flyers, XSS sanitization
- [x] **Fase 9** — Dashboard Insights: Fontes & Ofertas, Ranking, Insights (heatmap + outliers + melhores ofertas)
- [x] **Fase 10** — Brand Extraction + Email/TG UX: coluna brand no DB/dashboard, templates responsivos, SMTP Gmail, Ruff config
- [x] **Fase 11** — Correção de Constraints: UNIQUE (ingredient_id, store_id, collected_at) em prices e price_history, correção do scrape_frequencies, tratamento de erro 42P10

## Contribuindo

Este é um projeto pessoal, mas sugestões e PRs são bem-vindos.
