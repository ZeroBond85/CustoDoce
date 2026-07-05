---
doc_type: snapshot
slug: raio-x_custo_doce_resumido
current_version: 0.0.0
truth_at:
  tests_total: 805
  pages_count: 19
---
# 🍬 CUSTO DOCE — RAIO-X RESUMIDO
> Última revisão: 2026-07-05 19:08 UTC
## Visão Executiva e Estratégica do Projeto

---

## 🎯 1. ELEVATOR PITCH

O CustoDoce é um sistema que **automatiza a busca e comparação de preços de ingredientes para confeitaria**, eliminando horas de trabalho manual do confeiteiro e garantindo que ele sempre pague o menor preço possível na Baixada Santista e São Paulo.

---

## 💡 2. PROPOSTA DE VALOR

Confeiteiros perdem horas por semana visitando mercados, catálogos e sites para comparar preços de ingredientes como leite condensado, chocolate e farinha. O CustoDoce resolve isso coletando automaticamente preços de 51 lojas (atacados, e-commerces e agregadores), normalizando tudo para R$/kg e apresentando o ranking de menores preços em segundos via Dashboard web ou Telegram.

O diferencial está no **pipeline de matching com IA de 6 estágios**: combina regras exatas, fuzzy matching (RapidFuzz), embeddings semânticos (Sentence-Transformers ONNX) e classificação por LLM (Groq/OpenRouter/HF) para identificar corretamente produtos equivalentes mesmo quando têm nomes diferentes em lojas distintas — algo que sistemas simples de busca por palavra-chave não conseguem fazer. Tudo isso opera **100% em infraestrutura gratuita** (Supabase Free Tier, GitHub Actions, Streamlit Cloud).

---

## 📊 3. PÚBLICO-ALVO E MERCADO

| Item | Detalhe |
| :--- | :--- |
| **Quem usa** | Confeiteiros profissionais e amadores, padarias, docerias, confeitarias artesanais |
| **Região** | Baixada Santista (Santos, São Vicente, Praia Grande, Mongaguá, Itanhaém, Peruíbe) + São Paulo Capital |
| **Mercado** | Confeitaria artesanal brasileira em crescimento — alta dos insumos torna a comparação de preços cada vez mais relevante |
| **Concorrência indireta** | Busca manual em marketplaces, grupos de WhatsApp, planilhas próprias |

---

## 🧰 4. TECNOLOGIA EM ALTO NÍVEL

| Camada | Tecnologia | Por que foi escolhida? |
| :--- | :--- | :--- |
| Interface | **Streamlit** | Rápido de desenvolver, gratuito no Cloud, 18 módulos analíticos |
| Banco de Dados | **Supabase (PostgreSQL 15)** | Gratuito (500 MB), autenticação embutida, RLS, RPCs |
| Orquestração | **GitHub Actions** | Automação de scraping 2x/dia sem custo (2.000 min/mês) |
| IA/Matching | **Sentence-Transformers ONNX + Groq LLM** | Pipeline de 6 estágios com fallback entre 3 providers de LLM |
| Anomalias | **Scikit-learn Isolation Forest** | Detecção de outliers de preço para evitar dados poluídos |
| Bot | **Telegram Bot API** | Consultas rápidas mobile (6 comandos) |
| Logging | **Structlog + OpenTelemetry** | Observabilidade estruturada e tracing |

---

## 🚀 5. PRINCIPAIS DIFERENCIAIS COMPETITIVOS

1. **Pipeline de Matching Multi-Estágio:** 6 níveis de verificação (exato → fuzzy → embeddings ONNX → LLM com 3 providers + circuit breaker). Precisão estimada ~85-90% com auto-aprendizado de aliases.

2. **Custo Zero (Free Tier):** Infraestrutura 100% gratuita — Supabase (500 MB DB), GitHub Actions (2.000 min/mês), Streamlit Cloud (1 app privado), Gmail SMTP (500 e-mails/dia). Viável para MVP sem investimento inicial.

3. **Multi-Canal de Acesso:** Dashboard Web (18 telas analíticas) + Telegram Bot (consultas rápidas) + Relatórios Diários por E-mail.

4. **Calculadora de Receitas Inteligente:** Calcula custo real (monofonte ou multifonte) baseado nos preços atuais do banco, com overhead, margem de lucro e sugestão de lojas mais baratas.

5. **Alertas Proativos:** Notificação automática quando um ingrediente cai ≥10% ou quando um item monitorado fica sem atualização por mais de 48h.

---

## 📈 6. MÉTRICAS DE SUCESSO (KPIs)

| Métrica | Valor Atual | Notas |
| :--- | :--- | :--- |
| Ingredientes monitorados | **23** canônicos (leite condensado, chocolate, farinha, etc.) | Expansível via YAML |
| Lojas/fornecedores | **51** lojas em 4 tiers (PDF, API VTEX, sites, manual) | Cobre atacados + e-commerces |
| Precisão do Matching | **~85-90%** estimado | Via pipeline 6 estágios + fila de revisão manual |
| Testes automatizados | **577** testes (483 unit + 94 schema) + 13 integration files + 6 real — atualizado 2026-06-30 (era 512 em 29/06; Sprint 7-9 adicionou 26 testes + 23 feature tests + 3 menu-group tests) | Pendente: E2E (Playwright requer setup) |
| Dashboard | **18** módulos analíticos (era 17; promocoes integrada) | Visão geral, preços, histórico, ranking, calculadora, scrapers, promocoes, etc. |
| Alertas configurados | 5 triggers de alerta (price_drop, scrape_failure, etc.) | 3 canais: e-mail, Telegram, WhatsApp |
| Consumo GitHub Actions | **~400 min/mês** de 2.000 disponíveis | Margem para 5x expansão |
| Pre-push hook | **~30s** local sem unit tests (rápido) | opt-in `CI_LOCAL_UNIT=1` adiciona full unit suite |
| Tempo CI local | **~3 min** completo (lint + typecheck + unit + schema) | Roda offline pré-push e no GitHub Actions |

---

## ⚠️ 7. RISCOS E DECISÕES ESTRATÉGICAS

| # | Risco de Negócio | Impacto | Plano de Mitigação |
| :--- | :--- | :--- | :--- |
| 1 | **Dependência de Free Tier:** Limites de armazenamento/ação podem estourar com crescimento | ⚠️ Médio | Cleanup automático (prices 90d, logs 30d). Migrar para planos pagos ao atingir 50+ usuários ativos. |
| 2 | **Qualidade dos Dados:** Matching impreciso faz o usuário perder confiança | 🔴 Alto | Review Queue com aprovação manual + auto-aprendizado de aliases (se semântica ≥0.75). |
| 3 | **Segurança da Service Role:** Chave de admin exposta no dashboard | 🔴 Alto → 🟡 Reduzido (29/06) | ✅ Sprint 1.1 mitigou UI dashboard (tabs `.env`/YAML removidas). `dashboard_queries.py` usa apenas `get_supabase()` (anon). `get_service_client()` ainda em `price_repository.py:26` mas é chamado apenas pelo collector pipeline (GitHub Actions server-side). Falta: criar role `dashboard_user` com RLS mínimas. |
| 4 | **Falta de Cobertura de Testes:** Testes unitários existem (483), mas integração e E2E são frágeis | 🟠 Alto → 🟡 Reduzido (30/06) | ✅ Sprint 2.2 zerou risco de porta 5432 no CI (conftest migrado para RPC POSTGREST 443). Contract tests novos em `test_dashboard_contracts.py`. Sprint 7-9 (+65). Pendente: 3 E2E Playwright requerem setup. |
| 5 | **Concorrência:** Grandes players (marketplaces) podem lançar soluções similares | 🟡 Médio | Foco em regionalidade (Baixada Santista) + atendimento personalizado + dados históricos como barreira de saída. |

---

## 🗺️ 8. ROADMAP ESTRATÉGICO

| Fase | Objetivo | Principais Entregas | Prazo |
| :--- | :--- | :--- | :--- |
| **Atual** | MVP Consolidado | 51 lojas, 23 ingredientes, **577 testes** (era 512), 18 telas, Telegram, alertas, calculadora | Concluído |
| **Pós-MVP ✅ (Fase 9 + Sprint 1 + Sprint 2, 28-29/06)** | Higiene & Robustez | ✅ CI Hygiene (filter-branch removeu 11 arquivos sensíveis; pack 444MB→8.7MB); ✅ Pillow 12.2.0 patched / Dependabot 7 alerts dismissed; ✅ Pre-push Python rewrite + auditoría-secrets; ✅ Sprint 1.1: `.env` editor & `stores.yaml` editor removidos do dashboard; ✅ Sprint 1.2: Bot Telegram agora lê do DB (`config_db.get_active_ingredients()`) com fallback YAML; fuzzy search `rapidfuzz.fuzz.token_set_ratio`; paginação inline keyboard; ✅ Sprint 1.3-1.5: Mobile CSS, Query Params URL↔session_state, Acessibilidade (skip-link + prefers-reduced-motion); ✅ Sprint 2.1-2.4: Test Hardening (normalizer 11→32 casos), conftest migrated para RPC 443, contract tests dashboard_queries, `CI_LOCAL_UNIT=1` opt-in. | Concluído |
| **Curto Prazo** | Confiabilidade | Finalizar role `dashboard_user` (segurança residual) + sanitizar RPCs (GRANT EXECUTE TO service_role ONLY) + finalizar setup Playwright para E2E + fallback no normalizer para "un"/"pacote" + implementar Peso Mínimo (`unit_kg < 0.01` ignora) | 1-2 meses |
| **Médio Prazo** | Escalabilidade | Expansão para novas regiões (interior SP), novas fontes de dados, cache Redis, self-learning de aliases | 3-6 meses |
| **Longo Prazo** | Diferencial | Previsão de preços (IA), painel de tendências, recomendação de substituição de marcas, app mobile | 6-12 meses |

---

## ⚡ 9. QUICK WINS (Alto Impacto, Baixo Esforço)

Oportunidades que podem ser implementadas em dias/semana e geram valor real:

| # | Oportunidade | Esforço | Impacto | Por que agora |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Finalizar segurança da service_role** — Restringir RPCs (GRANT) e criar role `dashboard_user` com RLS mínimas | 1-2d | 🔴 Residual | Sprint 1.1 mitigou o UI (tabs sensíveis removidas, dashboard_queries não toca service_role). Falta endurecer a camada DB. |
| 2 | **Cache LRU no dashboard** — TTL em vez de LRU infinito | 1-2d | 🟡 Médio | ✅ Sprint 1.x adicionou `@lru_cache` em `dashboard_queries.py:39-104` e `cached_get_*`. Falta TTL real para mutações (clear_all_caches centraliza). |
| 3 | ~~**Busca fuzzy no Telegram** — `/preco condensado` achar "Leite Condensado"~~ ✅ | — | — | **RESOLVIDO em Sprint 1.2** (28/06). `handlers.py:38` agora usa `rapidfuzz.fuzz.token_set_ratio` + lê ingredientes do DB. |
| 4 | **Fallback de unidade no normalizer** — Se kg falha, usar "un" como fallback | 1d | 🟡 Médio | Sprint 2.1 expandiu testes (`test_normalizer.py` 11→32 casos) documentando o comportamento, mas não fix. Casos `un`/`1un`/`pacote`/`1l` continuam retornando `None`. |
| 5 | **Peso mínimo** — Ignorar produtos com unit_kg < 0.01 (ex: 1g distorce média) | 0.5d | 🟢 Leve | Não implementado. Evita outliers que poluem rankings e alertas. |

---

## 💡 10. IDEIAS PARA EXPLORAR (Inovação)

Funcionalidades que já têm 80% dos dados prontos — só conectar:

| Ideia | O que existe hoje | O que falta |
| :--- | :--- | :--- |
| **Push de "menor preço histórico"** | Sistema de alertas (alert_rules), detecção de anomalias (Isolation Forest), canal Telegram | Conectar o trigger de "new_low_price" ao envio pro Telegram |
| **Recomendação de substituição** | Dados de marca (brand_extractor), preço por ingrediente, matching semântico | Lógica que compara marcas do mesmo ingrediente e sugere troca |
| **Calculadora de lote econômico** | Normalizer já calcula R$/kg e R$/un para qualquer produto | UI que pergunta "quantas unidades por semana?" e calcula se vale comprar o pack |
| **Self-learning de aliases** | Auto-aprender alias já existe na review_queue (se semântica ≥0.75) | Expandir para sugerir aliases automaticamente sem revisão manual |
| **Relatório semanal de tendências** | Dados históricos (90d), price_trends, longitudinal_winners | Template HTML + envio agendado (já existe scheduler) |

---

## 🛠️ 11. AÇÕES PRIORITÁRIAS (O Que Fazer Agora)

Cada item tem: contexto, passo a passo resumido, esforço e como testar.

---

### 🔴 Crítico (dias)

#### 1. Service Role exposta no Dashboard
**Problema:** `price_repository.py` usa a chave de admin (`SERVICE_ROLE_KEY`) dentro do Streamlit. Se o dashboard for comprometido, invasor tem controle total do banco (DELETE, TRUNCATE).

**Passo a passo:**
1. Criar role `dashboard_user` no Supabase com permissão só de SELECT + INSERT na review_queue
2. Gerar credenciais JWT para essa role
3. Trocar o cliente do dashboard para usar `anon_key` + JWT restrito
4. Remover `get_service_client()` do código do dashboard

**Esforço:** 2-3 dias · **Verificação:** Dashboard consegue ler dados mas INSERT em `prices` falha

---

#### 2. RPC `exec_sql_query` sem proteção
**Problema:** Função no banco aceita SQL arbitrário e roda como admin. Combinada com o vazamento da service_role (item 1), permite invasão total.

**Passo a passo:**
1. Restringir acesso: `GRANT EXECUTE TO service_role ONLY`
2. Remover dependência do script de deploy
3. Testar que anon key não consegue chamar

**Esforço:** 1 dia · **Verificação:** Chamar o RPC com `anon_key` → erro

---

### 🟠 Alto (semana)

#### 3. Testes E2E não funcionam
**Problema:** Pasta `tests/e2e/` tem 3 arquivos mas nenhum teste roda. Sem E2E, mudanças no dashboard quebram sem alerta.

**O que fazer:** Configurar Playwright no CI, criar fixture de login, escrever 3 testes (login, navegação, preços)

**Esforço:** 3-5 dias

#### 4. Dashboard sem cache
**Problema:** Toda consulta vai direto ao Supabase. Latência em cada carregamento de página.

**O que fazer:** Adicionar `TTLCache` de 5 min nas 3 queries mais usadas + botão "Limpar cache" na sidebar

**Esforço:** 2 dias

---

### 🟡 Médio (melhorias rápidas)

| # | Problema | Solução | Esforço |
| :--- | :--- | :--- | :--- |
| 5 | Busca no Telegram é `startswith` — `/preco condensado` não acha | ~~Usar `fuzz.token_set_ratio` (RapidFuzz) igual ao matcher~~ | ~~1 dia~~ | ✅ Sprint 1.2 (28/06). `handlers.py:38` agora faz fuzzy + lê ingredientes do DB. |
| 6 | Se `parse_unit()` falha, o produto é perdido | Fallback: tratar como 1 unidade se unidade não reconhecida | 1 dia | Em aberto. Sprint 2.1 documentou o comportamento via testes (32 casos). Falta implementar fallback default. |
| 7 | Produtos com peso < 0.01kg (ex: 1g) distorcem média | Ignorar no normalizer se `unit_kg < 0.01` | 0.5 dia | Em aberto. |

---

### ✅ Resolvidos

| Item | Resolvido em |
| :--- | :--- |
| Raio-X desatualizado (contagens erradas) | 27/06/2026 |
| CI Hygiene (Fase 9): pack 444MB→8.7MB, 11 arquivos sensíveis removidos via `git filter-branch`, 7 Dependabot dismissed, pre-push Python rewrite, `lint/typecheck/docs-sync/unit/integration/deploy-check` CI jobs | 28/06/2026 |
| Sprint 1.1 — Segurança Dashboard: `.env` editor e `stores.yaml` editor removidos da UI; banner info "YAML synced from DB" adicionado | 28/06/2026 |
| Sprint 1.2 — Bot DB Sync: `handlers.py` reescrito lê ingredientes do DB (`config_db.get_active_ingredients()`) com fallback YAML; fuzzy search `rapidfuzz.fuzz.token_set_ratio`; paginação inline keyboard | 28/06/2026 |
| Sprint 1.3 — Mobile CSS: media queries 768px/640px, sidebar rail, tabelas sticky first column, safe-area padding, chart height limit | 28/06/2026 |
| Sprint 1.4 — Query Params: `precos.py`, `historico.py`, `calculadora.py` sincronização bidirecional URL↔session_state | 28/06/2026 |
| Sprint 1.5 — Acessibilidade: skip-link "Pular para conteúdo", focus-visible, `prefers-reduced-motion`, `font-variant-numeric: tabular-nums` | 28/06/2026 |
| Sprint 2.1 — Test Hardening: `test_normalizer.py` expandido de 11 para 32 casos parametrizados (cobre todas as unidades reais + edge cases) | 29/06/2026 |
| Sprint 2.2 — CI Safety: `tests/conftest.py` migrado para `get_service_client().rpc("exec_sql_query")` (porta 443), eliminando risco de bloqueio 5432 no CI | 29/06/2026 |
| Sprint 2.3 — Contract Tests: novo `test_dashboard_contracts.py` valida shape dos dados consumidos pelo dashboard (KPIs, coverage, promotions, scraper health) — 4 tests críticos sem precisar de DB real | 29/06/2026 |
| Sprint 2.4 — Developer UX: hook `pre-push` agora suporta `CI_LOCAL_UNIT=1` para opt-in de testes unitários antes do push | 29/06/2026 |

---

## 🔄 12. COMO MANTER ESTE DOCUMENTO ATUALIZADO

**Este documento é uma "fotografia executiva" do projeto na data de hoje.** Para garantir que ele reflita sempre a realidade, siga estas instruções:

| Método | O que fazer | Quando fazer |
| :--- | :--- | :--- |
| **Atualização Completa** | Use a IA para re-extrair as informações do `CUSTO_DOCE_RAIO_X.md` e do código-fonte, depois peça para regenerar este resumo mantendo a estrutura. | A cada grande marco (ex: nova funcionalidade relevante, mudança de stack, ou a cada 2 meses). |
| **Atualização Rápida** | Descreva a mudança (ex: "Adicionamos 10 novas lojas" ou "Precisão do matching subiu para 93%") e peça para a IA atualizar as seções afetadas. | Mudanças pontuais entre grandes marcos. |

**Versão Atual:** v4.0  
**Última Atualização:** 30/06/2026

---

## 📜 13. HISTÓRICO DE VERSÕES

| Versão | Data | Autor | Mudanças |
| :--- | :--- | :--- | :--- |
| v4.0 | 30/06/2026 | IA + Eric | Streamlit 1.58 full modernization (Sprint 7-9): `st.navigation()` menu nativo (5 grupos), promocoes integrada (18 páginas), `st.dialog()` confirmação, `st.pagination()` com bind query-params, batch form config, responsive KPIs, bar chart substitui heatmap quebrado, spinners em 6 páginas, labels acessíveis, email_service hardening, 23 novos testes. Testes: 512→**577** (+65). Nota geral: **9.0/10**. |
| v3.0 | 29/06/2026 | IA + Eric | Atualização pós-Sprint 1+2 e Fase 9. Testes: 477→512. Riscos #3 e #4 recalibrados (mitigados parcialmente). Roadmap Curto Prazo substituído por **linha "Pós-MVP ✅"** cruzando todas as entregas dos últimos dias. Quick Wins #2 (cache LRU) e #3 (Telegram fuzzy) marcados como resolvidos (LRU parcial). Tabela ✅ Resolvidos expandida com 11 entradas detalhadas (Fase 9 + Sprint 1.1-1.5 + Sprint 2.1-2.4). Patches narrativos mantêm coerência cronológica (v2.0→v3.0 in-place, sem novo arquivo). |
| v1.2 | 27/06/2026 | IA | Adicionado seção 11 (Ações Prioritárias) com 7 itens ordenados por impacto. Fusão do PLANO_ACAO_PRIORITARIO.md. |
| v1.1 | 27/06/2026 | IA | Adicionado seções 9 (Quick Wins) e 10 (Ideias para Explorar). |
| v1.0 | 27/06/2026 | IA | Criação do documento resumido baseado no CUSTO_DOCE_RAIO_X.md. |
