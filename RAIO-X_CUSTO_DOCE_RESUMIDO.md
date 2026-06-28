# 🍬 CUSTO DOCE — RAIO-X RESUMIDO
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
| Interface | **Streamlit** | Rápido de desenvolver, gratuito no Cloud, 17 módulos analíticos |
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

3. **Multi-Canal de Acesso:** Dashboard Web (17 telas analíticas) + Telegram Bot (consultas rápidas) + Relatórios Diários por E-mail.

4. **Calculadora de Receitas Inteligente:** Calcula custo real (monofonte ou multifonte) baseado nos preços atuais do banco, com overhead, margem de lucro e sugestão de lojas mais baratas.

5. **Alertas Proativos:** Notificação automática quando um ingrediente cai ≥10% ou quando um item monitorado fica sem atualização por mais de 48h.

---

## 📈 6. MÉTRICAS DE SUCESSO (KPIs)

| Métrica | Valor Atual | Notas |
| :--- | :--- | :--- |
| Ingredientes monitorados | **23** canônicos (leite condensado, chocolate, farinha, etc.) | Expansível via YAML |
| Lojas/fornecedores | **51** lojas em 4 tiers (PDF, API VTEX, sites, manual) | Cobre atacados + e-commerces |
| Precisão do Matching | **~85-90%** estimado | Via pipeline 6 estágios + fila de revisão manual |
| Testes automatizados | **617** testes (417 unit + 94 schema + 100 integration + 6 real) | Pendente: E2E (Playwright requer setup) |
| Dashboard | **17** módulos analíticos | Visão geral, preços, histórico, ranking, calculadora, scrapers, etc. |
| Alertas configurados | 5 triggers de alerta (price_drop, scrape_failure, etc.) | 3 canais: e-mail, Telegram, WhatsApp |
| Consumo GitHub Actions | **~400 min/mês** de 2.000 disponíveis | Margem para 5x expansão |

---

## ⚠️ 7. RISCOS E DECISÕES ESTRATÉGICAS

| # | Risco de Negócio | Impacto | Plano de Mitigação |
| :--- | :--- | :--- | :--- |
| 1 | **Dependência de Free Tier:** Limites de armazenamento/ação podem estourar com crescimento | ⚠️ Médio | Cleanup automático (prices 90d, logs 30d). Migrar para planos pagos ao atingir 50+ usuários ativos. |
| 2 | **Qualidade dos Dados:** Matching impreciso faz o usuário perder confiança | 🔴 Alto | Review Queue com aprovação manual + auto-aprendizado de aliases (se semântica ≥0.75). |
| 3 | **Segurança da Service Role:** Chave de admin exposta no dashboard | 🔴 Alto | Já identificado. Criar role `dashboard_user` com permissões restritas. |
| 4 | **Falta de Cobertura de Testes:** Testes unitários existem (417), mas integração e E2E são frágeis | 🟠 Alto | Priorizar testes E2E e de integração na próxima fase. |
| 5 | **Concorrência:** Grandes players (marketplaces) podem lançar soluções similares | 🟡 Médio | Foco em regionalidade (Baixada Santista) + atendimento personalizado + dados históricos como barreira de saída. |

---

## 🗺️ 8. ROADMAP ESTRATÉGICO

| Fase | Objetivo | Principais Entregas | Prazo |
| :--- | :--- | :--- | :--- |
| **Atual** | MVP Consolidado | 51 lojas, 23 ingredientes, 617 testes, 17 telas, Telegram, alertas, calculadora | Concluído |
| **Curto Prazo** | Confiabilidade | Testes E2E + role `dashboard_user` (segurança) + sanitizar RPCs + cache no dashboard | 1-2 meses |
| **Médio Prazo** | Escalabilidade | Expansão para novas regiões (interior SP), novas fontes de dados, cache Redis, self-learning de aliases | 3-6 meses |
| **Longo Prazo** | Diferencial | Previsão de preços (IA), painel de tendências, recomendação de substituição de marcas, app mobile | 6-12 meses |

---

## ⚡ 9. QUICK WINS (Alto Impacto, Baixo Esforço)

Oportunidades que podem ser implementadas em dias/semana e geram valor real:

| # | Oportunidade | Esforço | Impacto | Por que agora |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Corrigir segurança da service_role** — Criar role `dashboard_user` no Supabase | 2-3d | 🔴 Crítico | Remove risco de vazamento total do banco. Sem isso, qualquer vulnerabilidade no Streamlit expõe todos os dados. |
| 2 | **Cache LRU no dashboard** — TTL 5min nas consultas mais frequentes | 2d | 🟡 Médio | Dashboard fica mais responsivo, reduz latência e custo de banda do Supabase. |
| 3 | **Busca fuzzy no Telegram** — `/preco condensado` achar "Leite Condensado" | 1d | 🟡 Médio | UX do bot melhora drasticamente sem exigir nome exato. |
| 4 | **Fallback de unidade no normalizer** — Se kg falha, usar "un" como fallback | 1d | 🟡 Médio | Recupera produtos que hoje são perdidos por unidade não reconhecida. |
| 5 | **Peso mínimo** — Ignorar produtos com unit_kg < 0.01 (ex: 1g distorce média) | 0.5d | 🟢 Leve | Evita outliers que poluem rankings e alertas. |

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
| 5 | Busca no Telegram é `startswith` — `/preco condensado` não acha | Usar `fuzz.token_set_ratio` (RapidFuzz) igual ao matcher | 1 dia |
| 6 | Se `parse_unit()` falha, o produto é perdido | Fallback: tratar como 1 unidade se unidade não reconhecida | 1 dia |
| 7 | Produtos com peso < 0.01kg (ex: 1g) distorcem média | Ignorar no normalizer se `unit_kg < 0.01` | 0.5 dia |

---

### ✅ Resolvidos

| Item | Resolvido em |
| :--- | :--- |
| Raio-X desatualizado (contagens erradas) | 27/06/2026 |

---

## 🔄 12. COMO MANTER ESTE DOCUMENTO ATUALIZADO

**Este documento é uma "fotografia executiva" do projeto na data de hoje.** Para garantir que ele reflita sempre a realidade, siga estas instruções:

| Método | O que fazer | Quando fazer |
| :--- | :--- | :--- |
| **Atualização Completa** | Use a IA para re-extrair as informações do `CUSTO_DOCE_RAIO_X.md` e do código-fonte, depois peça para regenerar este resumo mantendo a estrutura. | A cada grande marco (ex: nova funcionalidade relevante, mudança de stack, ou a cada 2 meses). |
| **Atualização Rápida** | Descreva a mudança (ex: "Adicionamos 10 novas lojas" ou "Precisão do matching subiu para 93%") e peça para a IA atualizar as seções afetadas. | Mudanças pontuais entre grandes marcos. |

**Versão Atual:** v1.2  
**Última Atualização:** 27/06/2026

---

## 📜 13. HISTÓRICO DE VERSÕES

| Versão | Data | Autor | Mudanças |
| :--- | :--- | :--- | :--- |
| v1.2 | 27/06/2026 | IA | Adicionado seção 11 (Ações Prioritárias) com 7 itens ordenados por impacto. Fusão do PLANO_ACAO_PRIORITARIO.md. |
| v1.1 | 27/06/2026 | IA | Adicionado seções 9 (Quick Wins) e 10 (Ideias para Explorar). |
| v1.0 | 27/06/2026 | IA | Criação do documento resumido baseado no CUSTO_DOCE_RAIO_X.md. |
