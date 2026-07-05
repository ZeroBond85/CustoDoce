# CustoDoce — Buscador de Preços para Confeitaria 🍰
> Última atualização: 2026-07-05 19:08 UTC

![Build Status](https://img.shields.io/github/actions/workflow/status/CustoDoce/ci.yml?branch=master)
![Version](https://img.shields.io/badge/version-19.546.94--mvp-blue)
![License](https://img.shields.io/badge/license-Personal-green)
![Deploy](https://img.shields.io/badge/deploy-production%20%7C%20staging-brightgreen)

Sistema automatizado de busca e comparação de preços de ingredientes para confeitaria, focado na **Baixada Santista** (Santos, São Vicente, Praia Grande, Mongaguá, Itanhaém, Peruíbe) e **São Paulo Capital**. Infraestrutura otimizada para operar 100% no **Free Tier**.

## 🚀 Funcionalidades Principais

- 🔍 **Coleta Automatizada**: Varredura 2x/dia de PDFs de atacados, APIs VTEX, sites de e-commerce e agregadores.
- 🤖 **Inteligência de Matching**: Pipeline multi-estágio (Exato → Alias → Fuzzy → Semantic Embeddings → LLM Groq → Review Queue).
- 📊 **Dashboard Analítico**: 19 módulos especializados incluindo visão geral, histórico de preços, ranking de fontes, promoções, insights de outliers e health de scrapers.
- 📱 **Telegram Bot**: Consultas instantâneas via `/preco <ingrediente>`, lista de monitorados e status do sistema, com fuzzy search e paginação inline.
- 🧮 **Calculadora de Receitas**: Cálculo de custo real baseado nos preços atuais do banco, com salvamento de receitas e cenários de margem.
- 📧 **Relatórios Diários**: Envio automático de resumo de melhores preços via Gmail SMTP.
- ⚙️ **Configuração Declarativa**: Controle de funcionalidades via `config/features.yaml` sem necessidade de alteração de código.
- 📱 **Responsivo**: CSS adaptativo para mobile (640px/768px/1280px), tabelas com sticky columns, sidebar compacta.
- ♿ **Acessibilidade**: Skip-link "Pular para conteúdo", focus-visible, `prefers-reduced-motion`, `tabular-nums` em métricas.
- 🔗 **Query Params**: Sincronização URL ↔ session_state nas páginas Preços, Histórico e Calculadora (sem loop de rerender).
- 🔒 **Segurança**: Tabs de edição `.env` e YAML removidas do dashboard (config.py, lojas.py); banner info de sync YAML→DB.
- ✅ **Smoke Test Real**: `scripts/validate_dashboard_queries.py` valida 10 queries contra Supabase real no CI pós-deploy (pega schema mismatch antes do usuário ver).
- 🛠️ **Infraestrutura Robusta**: CI/CD com 7 jobs, validação de schema via RPC, ONNX para performance de ML e rate limiting.

## 📋 REGRAS DE NEGÓCIO

### Pipeline de Matching
Para garantir que "Leite Condensado Moça 395g" seja identificado corretamente como "Leite Condensado Integral", utilizamos um fluxo de confiança:
1. **Match Exato**: Busca o nome canônico ou apelidos exatos no texto do produto.
2. **Contido**: Verifica se todas as palavras do ingrediente estão presentes no nome do produto.
3. **Fuzzy (RapidFuzz)**: Calcula a similaridade de tokens. Matches $\ge 80\%$ são aceitos automaticamente.
4. **Semantic Blend**: Para casos duvidosos ($55\% - 80\%$), combinamos a similaridade de texto com Embeddings de Vetores (ONNX).
5. **LLM Classifier (Groq)**: Em zona cinzenta, a IA analisa o contexto para decidir o ingrediente.
6. **Review Queue**: Tudo que não atinge a confiança mínima vai para revisão humana no Dashboard.

### Cálculo de Preços e Normalização
- **Normalização**: Todos os produtos são convertidos para a unidade base (**R$/kg** ou **R$/un**) para permitir comparação justa (ex: lata de 395g $\rightarrow$ preço por kg).
- **Detecção de Outliers**: Utilizamos Z-Score e Isolation Forest para marcar preços irreais (erros de digitação do mercado) e evitar que poluam o ranking.
- **Confiabilidade**: Cada preço possui um score de confiança baseado no método de matching utilizado.

### Calculadora de Receitas
- **Auto-fill**: Ao adicionar um ingrediente, o sistema busca automaticamente o melhor preço atual no banco de dados.
- **Margem de Lucro**: Permite definir a porcentagem de lucro desejada para calcular o preço final de venda do doce.
- **Custo Histórico**: Possibilidade de analisar a variação do custo de uma receita ao longo do tempo.

### Alertas e Notificações
- **Variação de Preço**: Notificações proativas quando um ingrediente essencial sofre queda ou alta brusca ($\ge 15\%$).
- **Relatórios Diários**: Resumo matinal com os "Winners" do dia enviado por e-mail.
- **Alertas de Cobertura**: Aviso se algum ingrediente monitorado não recebe atualização de preço há mais de 48h.

### Segurança e Permissões
- **RLS (Row Level Security)**: O banco de dados Supabase impede que o Dashboard altere dados sensíveis, permitindo apenas leitura via `anon key`.
- **Admin Password**: Acesso ao dashboard é protegido por senha via Streamlit Secrets.
- **Service Role**: Operações de escrita (scrapers) utilizam a `service_role key`, isolada do acesso público.

## 🧭 FLUXOS DE USUÁRIO

### Fluxo de Coleta Automática
`GitHub Actions (Cron)` $\rightarrow$ `Sync Store Fields` $\rightarrow$ `Scrapers (PDF/API/Web)` $\rightarrow$ `Normalizer` $\rightarrow$ `Matcher Pipeline` $\rightarrow$ `Supabase RPC` $\rightarrow$ `Price Intelligence (Anomalias)` $\rightarrow$ `Relatório E-mail`.

### Fluxo de Consulta via Telegram
`/preco <ingrediente>` $\rightarrow$ `Search Supabase` $\rightarrow$ `Filter Best Prices` $\rightarrow$ `Format Message` $\rightarrow$ `Telegram Response`.

### Fluxo de Dashboard
`Login` $\rightarrow$ `Visão Geral (KPIs)` $\rightarrow$ `Análise de Preço` $\rightarrow$ `Ajuste de Flag (features.yaml)` $\rightarrow$ `Trigger Manual de Coleta`.

### Fluxo da Calculadora
`Criar Receita` $\rightarrow$ `Adicionar Ingredientes` $\rightarrow$ `Auto-fill Preços` $\rightarrow$ `Definir Margem` $\rightarrow$ `Calcular Preço Final` $\rightarrow$ `Salvar`.

## 🛠️ Tech Stack

| Camada | Tecnologia | Papel | Free Tier |
|--------|------------|-------|-----------|
| **Banco + API** | Supabase (PostgreSQL) | Armazenamento, RPCs e RLS | 500 MB |
| **Scrapers** | GitHub Actions | Orquestração e Coleta (Cron) | 2.000 min/mês |
| **Dashboard** | Streamlit Cloud | Interface de Administração e Análise | 1 app privado |
| **ML/AI** | Sentence-Transformers + Groq | Embeddings ONNX e Classificação LLM | Grátis / API Key |
| **Bot** | python-telegram-bot | Interface de consulta rápida | Grátis |
| **Email** | Gmail SMTP | Relatórios e Alertas | 500 e-mails/dia |

## 🔧 SEGURANÇA

- **Gestão de Credenciais**: Nenhuma chave é commitada. Utilizamos GitHub Secrets e Streamlit Secrets.
- **Isolamento de Banco**: Uso rigoroso de RLS para separar a camada de visualização da camada de escrita.
- **Proteção de API**: Implementação de rate limiting nos scrapers para evitar banimentos por excesso de requisições.
- **Env**: Variáveis de ambiente controladas via `.env` localmente e Secrets no CI/CD.

## ⚠️ LIMITES E ESCALABILIDADE

O sistema foi desenhado para o **Free Tier**, com as seguintes considerações:
- **Supabase (500MB)**: Suficiente para milhões de registros de preços. A política de cleanup remove preços com mais de 90 dias para manter o banco leve.
- **GitHub Actions (2000 min/mês)**: O consumo atual é de $\sim 400$ min/mês. Temos margem para expandir o número de lojas.
- **Escalabilidade**: Caso a demanda cresça, a migração para o plano *Pro* do Supabase e a utilização de proxies residenciais para scrapers são os próximos passos recomendados.

## ⚙️ Setup e Instalação
Para configurar o sistema do zero, siga o [Guia de Deployment detalhado](docs/deployment.md).

---

## 📱 Comandos do Telegram
- `/preco <ingrediente>` → Lista os melhores preços ordenados por R$/kg.
- `/lista` → Exibe todos os ingredientes monitorados por categoria.
- `/status` → Resumo de saúde do sistema, total de preços e confiabilidade.
- `/ajuda` → Guia de uso do bot.

---

## 📊 Módulos do Dashboard

| Aba | Função Principal | Como Usar | Ações Disponíveis |
|-----|------------------|------------|-------------------|
| **Visão Geral** | KPIs globais e alertas. | Acesse a home para ver o resumo do dia. | Monitorar variação de preços. |
| **Preços** | Busca detalhada e top 3. | Filtre por ingrediente na barra de busca. | Exportar lista para CSV. |
| **Histórico** | Evolução temporal. | Selecione o ingrediente e a loja no gráfico. | Analisar tendências sazonais. |
| **Flyers** | Galeria de encartes. | Navegue pelos PDFs coletados. | Validar extração de OCR. |
| **Revisão** | Fila de aprovação. | Analise itens com confiança $< 80\%$. | Aprovar ou Rejeitar match. |
| **Fontes & Ofertas** | Ranking de lojas. | Compare quem tem o melhor preço médio. | Detectar promoções reais. |
| **Promoções** | Ofertas ativas. | Visualize produtos com maior desconto. | Identificar oportunidades de compra. |
| **Ranking** | Comparativo direto. | Selecione 2 ou mais lojas para comparar. | Identificar a loja mais barata. |
| **Insights** | Análise de outliers. | Verifique a lista de "anomalias". | Validar se o preço é erro ou oferta. |
| **Lojas** | Gestão de lojas. | Edite tiers e status de ativação. | Ativar/Desativar lojas. |
| **Ingredientes** | Gestão de canônicos. | Adicione aliases ou termos de busca. | Refinar a precisão do matching. |
| **Calculadora** | Custos de receitas. | Crie sua receita e adicione itens. | Calcular custo e preço de venda. |
| **Capacity Planning** | Planejamento de capacidade. | Analise a frequência de coleta por loja. | Otimizar janelas de scraping. |
| **Scrapers** | Gatilhos de coleta. | Clique em "Run Scraper" para forçar coleta. | Monitorar logs em tempo real. |
| **Scraper Health** | Monitoramento. | Verifique a taxa de sucesso por loja. | Diagnosticar falhas de conexão. |
| **Relatórios** | Gestão de e-mails. | Configure o template do HTML. | Testar envio de e-mail. |
| **Configuração** | Secrets e Flags. | Alterne flags no `features.yaml`. | Ativar/Desativar módulos do sistema. |
| **Diagnóstico** | Health check. | Rode o teste de conexão com Supabase. | Validar latência da API. |
| **Alertas** | Regras de notificação. | Defina a $\%$ de variação para alerta. | Configurar e-mails de aviso. |

---

## 🏗️ Estrutura do Projeto

```
CustoDoce/
├── .github/workflows/    # CI/CD (Lint, Typecheck, Tests, Scrape, Deploy)
├── config/               # YAMLs de ingredientes, lojas e features
├── scrapers/             # Lógica de coleta (PDF, VTEX, Web, Playwright, OCR)
├── parsers/              # Normalização, Matching, Brand Extraction e LLM
├── services/             # Core Business (Supabase, Price, Alerts, Config, Auth)
├── dashboard/            # UI Streamlit (Pages, Components, Layout)
├── admin/                # Entrypoint do Dashboard (app.py)
├── telegram_bot/         # Handlers e lógica do Bot
├── supabase/             # SQL Seeds, Migrations e RPCs
├── scripts/              # Utilitários de Deploy, Audit e Sync
├── tests/                # Unit, Schema, Integration, E2E e Real tests
└── main.py               # Orquestrador principal da coleta
```

---

## 🏪 Tiers de Lojas

| Tier | Tipo | Frequência | Método de Coleta |
|------|------|------------|-------------------|
| **1** | PDF Direto | Semanal | `pdfplumber` + OCR Fallback |
| **2a** | E-commerce SP | Diária | API VTEX / JSON |
| **2b** | Atacado Físico | Mensal | Importação Manual (.xlsx) |
| **3** | Agregadores | Fallback | Playwright / SSR HTML |
| **4** | Manual | Sob Demanda | Planilha / WhatsApp |

---

## 📊 EXEMPLO DE USO

### Consulta no Telegram
**Usuário**: `/preco leite condensado`
**Bot**: 
> 🥛 **Leite Condensado Integral**
> 1. **Assaí**: R$ 5,49 (R$ 13,95/kg) ✅
> 2. **Atacadão**: R$ 5,60 (R$ 14,18/kg)
> 3. **Carrefour**: R$ 6,10 (R$ 15,41/kg)
> _Atualizado em: 27/06 08:00_

### Relatório Diário (E-mail)
Um e-mail HTML contendo a tabela de "Melhores Preços do Dia", destacando ingredientes que baixaram mais de 10% em relação à média da semana.

### Dashboard de Análise
Uma tela com um gráfico de linha mostrando que o preço do Chocolate Melken caiu 15% no Atacadão, disparando um alerta de "Oportunidade de Compra".

---

## 🧪 TESTES
O projeto possui uma suíte de testes rigorosa para garantir a estabilidade do MVP:
- **Unitários**: Validação de normalizadores, matchers e serviços (pytest).
- **Schema**: Verificação de tabelas, colunas e RPCs no Supabase.
- **Integration**: Testes de fluxo completo (Coleta $\rightarrow$ Banco).
- **E2E**: Testes de interface do Dashboard via Playwright.
- **Real**: Validação de scrapers contra sites reais (flaky/slow).

**Como rodar**: `python -m pytest tests/`

---

## 📝 GUIA DE CONTRIBUIÇÃO
Contribuições são bem-vindas! Siga os padrões:
- **Código**: Use Ruff para linting e Mypy para tipagem.
- **PRs**: Crie branches para cada feature (`feat/` ou `fix/`) e abra PR para a `main`.
- **Docs**: Atualize a documentação em `docs/` ao alterar funcionalidades.
Mais detalhes em [docs/contributing.md](docs/contributing.md).

---

## 🗺️ Roadmap de Desenvolvimento

- [x] **Fases 0-21**: Fundação, Scrapers, Dashboard, Matcher, CI/CD, Docs, Quality e Observabilidade.
- [x] **Fase 2.4**: Staging Environment (2º Supabase isolado, CI/CD unificado).
- [x] **Fase 4.1**: Observabilidade Estruturada (structlog + OpenTelemetry).
- [x] **Fase 4.4**: Feature Flags por Ingrediente (2 níveis: global + override).
- [x] **Fase 8 (Full Overhaul)**: LLM Resilience (Strategy Pattern, Circuit Breaker, 3 providers), Cache (SQLite + DB), Cart Optimizer (Monofonte/Multifonte), Capacity Planning Dashboard, CI/CD Unification com Makefile.
- [x] **Fase 9 (CI Hygiene + Cleanup)**: `git filter-branch` removeu 11 arquivos sensíveis (pack 444MB → 8.7MB), pre-push hook Python, `ci_local.py` (8 validators), Dependabot alerts resolvidos, lições #1-#10 documentadas, CI 100% verde.
- [x] **Sprint 1 (UX + Segurança)**: `.env`/YAML tabs removidos do dashboard; Bot lê ingredientes do DB com fallback YAML + fuzzy search; Mobile CSS (768/640px); Query Params URL↔session_state; Acessibilidade (skip-link, prefers-reduced-motion).
- [x] **Sprint 2 (Test Hardening + Contract Safety)**: `test_normalizer.py` expandido de 11 → 32 casos; conftest usa RPC POSTGREST 443; novo `test_dashboard_contracts.py` valida shape do dashboard; `CI_LOCAL_UNIT=1` opt-in para pre-push. **512 unit+schema + 102 integration + 10 design + 6 real = 630 total passing**.
- [x] **Sprint 5 (CI Hardening)**: TypeError FASE8 `render_login()` corrigido; backup RPC extraído (`scripts/rpc_backup.py`); warmup reescrito Playwright; e2e-smoke localhost sem continue-on-error; 14 workflows auditados (0 hashFiles/PYEOF/failure()).
- [x] **Sprint 6 (Migration Sync)**: httpx `<1.0` pin; login E2E polling 45s; migrations 004+005 incluídas; 709 total passing.
- [x] **Sprint 7-9 (Dashboard Modernization)**: `st.navigation()` menu nativo (5 grupos); promocoes integrada (18 páginas); `st.dialog()` + `st.pagination()` + batch form config + KPIs responsive + spinners + labels acessíveis + email hardening. **577 unit+schema = 745 total passing**.
- [x] **Sprint 10 (Documentation Hygiene)**: sync_docs.py 3 auto-fixers + `--strict` auditor + dedup fix; 40 stale refs corrigidos em 11 `.md`; validate_dashboard_queries.py load_dotenv fix; maintenance_service.py duration_seconds populado; capacity_planning já funcional via diagnostico.py.
- [x] **Sprint 10.5 (sync_docs v2)**: 5 módulos baseados em markdown-it para classificação heading-aware de stale refs (HISTORICAL/CURRENT/AMBIGUOUS). 19 matches analisados, 5 auto-corrigidos. 818 testes unitários. Flag `--sync`/`--analyze`. Lição #25 (novo código = novos testes).
- [ ] **Próximos Passos**: role `dashboard_user` (RLS mínimas), `GRANT EXECUTE TO service_role ONLY`, E2E Playwright setup, fallback normalizer unidades, sync_docs v2 integrado em CI (--check --analyze).

---

## 🧠 OpenCode Skills Strategy

This project uses **two layers of OpenCode skills**:

| Layer | Location | Purpose |
|-------|----------|---------|
| **Global** | `~/.config/opencode/skills/` | 17 universal skills usable in any project (scraping, code quality, testing, SQL, git, CI/CD, etc.) |
| **Local (CustoDoce)** | `.opencode/skills/` | 7 overlays that inject CustoDoce-specific context (Telegram commands, Supabase schema, dashboard pages, GHA workflows, etc.) |

**Why this works:**
- OpenCode merges both layers when you open **this repo** — you get universal patterns + project shortcuts.
- In any other project, only the **global layer** loads — clean, reusable skills.
- Overlays are tiny (~30-100 lines each), extend without duplication, and are versioned with the repo.
- Adding a new project? Just reuse the global skills. The overlays stay here.

**Key global skills** (in `~/.config/opencode/skills/`): `scraping-resilience`, `code-quality-pro`, `test-architect`, `api-design`, `code-review`, `debug-troubleshooting`, `docs-writer`, `git-workflow`, `github-actions`, `project-doc-sync`, `refactor-patterns`, `sql-optimizer`, `streamlit`, `telegram-bot`, `test-generation`, `humanizer`, `seo`, `ui-ux-pro-max`.

**CustoDoce overlays** (in `.opencode/skills/`): `telegram-bot`, `docs-writer`, `sql-optimizer`, `streamlit`, `api-design`, `github-actions`, `project-doc-sync`.

> To validate: open this repo in OpenCode → skills from both layers are listed. Open any other folder → only global skills appear.

---

## 📜 Licença
Projeto para fins de estudo e automação pessoal.
