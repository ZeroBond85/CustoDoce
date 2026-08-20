# Functional Audit Matrix - 7 Priority Pages
> Última atualização: 2026-08-17 22:00 UTC

## Legend
- ✅ = Funcionando corretamente
- ❌ = Problema identificado
- ⚠️ = Aviso (não bloqueia funcionalidade)
- N/A = Não se aplica

## Elementos por Página

### 1. Scrapers & Logs (scrapers.py)

| Elemento | Funcionalidade | Estados | Acessibilidade | Feedback | Observação |
|----------|---------------|---------|----------------|----------|------------|
| Tab "Status & Logs" | ✅ Navegação entre tabs | ✅ Hover visual | ✅ Skip link | ✅ Dados renderizam (Lesson #58 fix) | Coluna errors normalizada para string |
| Tab "Agendamentos" | ✅ Tabela editável | ⚠️ Somente display | ✅ Labels nos campos | ✅ Atualização via query_params | Dados vêm do Supabase |
| Tab "Health Check" | ✅ Botão executar | ✅ Spinner durante processamento | ✅ Foco visível | ✅ Resultado em JSON | Health check manual |
| Botão "Health Check Manual" | ✅ Executa script | ✅ Loading state | ✅ Botão primary | ✅ Resultado JSON | Usa scripts/heal_scrapers.py |
| Links de navegação | ✅ Navegação lateral | ✅ Focus order | ✅ Skip link | ✅ ARIA labels | Ordem: sidebar → main → footer |

### 2. Scraper Health (scraper_health.py)

| Elemento | Funcionalidade | Estados | Acessibilidade | Feedback | Observação |
|----------|---------------|---------|----------------|----------|------------|
| 4 Tabs (Health Overview, Cobertura, Latency, Raw Logs) | ✅ Navegação por tabs | ✅ Hover/active | ✅ Skip link | ✅ Cada tab carrega dado específico | Tab 3 (Raw Logs) usa mesma sanitização |
| KPIs (4 métricas) | ✅ Display de KPIs | ✅ Hover card | ✅ role=alert no info_box | ✅ Update via st.metric | Healthy/Degraded/Critical cores |
| Tabela Health Overview | ✅ Ordenável | ✅ Hover row | ✅ Contraste adequado | ✅ Atualização a cada execução | 4 colunas: store, status, last_run, latency |
| Gráfico Latency P95 | ✅ Chart plotly | ✅ Hover tooltip | ✅ Reduce motion respectado | ✅ Cores por success_rate | Verde/Amarelo/Vermelho |
| Tabela Raw Logs | ✅ Renderiza sem ArrowInvalid | ✅ Dados limpos | ✅ Contraste adequado | ✅ Paginação pendente | Mesma sanitização de scrapers.py |

### 3. Revisão (revisao.py)

| Elemento | Funcionalidade | Estados | Acessibilidade | Feedback | Observação |
|----------|---------------|---------|----------------|----------|------------|
| Filtros (slider, select) | ✅ Aplicar filtro | ✅ Hover | ✅ Labels claros | ✅ Atualização em tempo real | Min confiança, match_type |
| Bulk actions (aprovar/rejeitar) | ✅ Batching de itens | ✅ Confirmação via st.success | ✅ Labels dos botões | ✅ St.rerun após ação | Aprova/rejeita em lote |
| Por item: checkbox | ✅ Selecionar item | ✅ Estado visual | ✅ ARIA label opcional | ✅ Seleção individual | Key: sel_{item_id} |
| Expanders (top3 candidatos, diagnóstico) | ✅ Expandir/colapsar | ✅ Focus management | ✅ Labels descriptivos | ✅ Informações detalhadas | top3 + match_reason |
| Badge match_type | ✅ Cor + texto | ✅ Cores consistentes | ✅ role=status no cd-badge | ✅ Ícone + texto | Cores: verde/azul/laranja/laranja |
| Selectbox ingrediente (aprovação) | ✅ Selecionar ingrediente | ✅ Validação | ✅ Label "Aprovar como ingrediente" | ✅ Popula ing_options | Inclui "Selecione..." |
| Selectbox marca (brand_override) | ✅ Manter/alterar marca | ✅ Validação | ✅ Label "Marca:" | ✅ Duas opções | Manter automática + marca detectada |
| Botões Aprovar/Rejeitar por item | ✅ Ação individual | ✅ Tipo primary/secondary | ✅ Confirmação visual | ✅ St.rerun após ação | Keys: btn_approve_{id}, btn_reject_{id} |
| Botão Adicionar Alias | ✅ Criar alias | ✅ Validação prévia | ✅ Label "➕ Adicionar como Alias" | ✅ St.rerun após ação | Valida ingredient e raw_product |

### 4. Flyers (flyers.py)

| Elemento | Funcionalidade | Estados | Acessibilidade | Feedback | Observação |
|----------|---------------|---------|----------------|----------|------------|
| Slider "Últimos N dias" | ✅ Filtrar flyers | ✅ Hover | ✅ Label "Últimos N dias" | ✅ Atualização ao mudar | 1 a 60 dias |
| Selectbox "Fonte" | ✅ Filtrar por fonte | ✅ Hover | ✅ Label "Fonte: Todas/pdf/website/vtex/aggregator" | ✅ Atualização ao mudar | Inclui "Todas" |
| Grid de cards de flyer | ✅ Exibir lista | ✅ Hover card | ✅ Contraste adequado | ✅ Click → modal | 4 colunas responsivas |
| Botão "Ver detalhes" | ✅ Abrir modal | ✅ Focus management | ✅ Label "Ver detalhes" | ✅ Abre st.session_state | Key: flyer_{id} |
| Modal detalhes | ✅ Exibir info flyer | ✅ Fechar (×) | ✅ role=dialog | ✅ Confirmar exclusão | Inclui aviso "irreversível" |
| Botão "Fechar" no modal | ✅ Fechar modal | ✅ St.rerun | ✅ Botão secundário | ✅ Limpa state | key: close_flyer |
| Botão "Excluir" no modal | ✅ Excluir flyer | ✅ Dialog confirmação | ✅ type=primary | ✅ Aviso "irreversível" | Chama _confirm_delete_dialog |
| KPI "Produtos extraídos" | ✅ Display informativo | ✅ Tooltip opcional | ✅ Contraste adequado | ✅ Informativo secundário | Nº de produtos extraídos |

### 5. Lojas Pendentes (lojas_pendentes.py)

| Elemento | Funcionalidade | Estados | Acessibilidade | Feedback | Observação |
|----------|---------------|---------|----------------|----------|------------|
| 3 métricas (Pendentes, Com Endereço, Casadas) | ✅ Display KPI | ✅ Hover | ✅ role=alert no info_box | ✅ Cores adequadas | Contagem de registros |
| Bulk reject "lixo de teste" | ✅ Rejeitar lote | ✅ Confirmação st.success | ✅ type=secondary | ✅ St.rerun após ação | Prefixos: "Cleanup Store", "OCR Test" |
| Bulk reject "não-alimentar" | ✅ Rejeitar lote | ✅ Confirmação st.success | ✅ type=secondary | ✅ St.rerun após ação | Usa _is_food_store_name |
| Por loja: match_score progress | ✅ Barrinha de similaridade | ✅ Visual OK | ✅ Label "Similaridade" | ✅ Atualizado via DB | 0% a 100% |
| Expanders (endereço, região) | ✅ Expandir/colapsar | ✅ Focus management | ✅ Labels descriptivos | ✅ Informações complementares | endereço, neighborhood, city |
| Botão "Aprovar e Casar" | ✅ Aprovar + casar | ✅ type=primary | ✅ Confirmação visual | ✅ St.rerun + merge | Valida target_store |
| Selectbox "Casar com loja existente" | ✅ Selecionar loja alvo | ✅ Validação | ✅ Label "Casar com loja existente:" | ✅ Popula get_active_stores() | Inclui "Selecione..." |
| Botão "Criar Nova Loja" | ✅ Criar nova loja | ✅ type=primary | ✅ Confirmação visual | ✅ St.rerun após ação | Cria store + aprova registro |
| Botão "➕ Criar Nova Loja" | ✅ Criar nova loja | ✅ Confirmação | ✅ Validação de campos | ✅ St.rerun após ação | Dados: name, tier, city, source |
| Botão "❌ Rejeitar" (por item) | ✅ Rejeitar item | ✅ type=secondary | ✅ Confirmação visual | ✅ St.rerun após ação | key: reject_new_{id} |
| Expanders lojas aprovadas | ✅ Exibir lista | ✅ Focus management | ✅ Labels claros | ✅ Apenas leitura | Aprovadas via auto-promoção |

### 6. Preços (precos.py)

| Elemento | Funcionalidade | Estados | Acessibilidade | Feedback | Observação |
|----------|---------------|---------|----------------|----------|------------|
| 3 selectboxes (ingrediente, loja, tier) | ✅ Filtros server-side | ✅ Hover | ✅ Labels claros | ✅ query_params sync | Atualiza URL |
| Query "Carregando preços..." | ✅ Spinner durante fetch | ✅ Loading state | ✅ Contraste adequado | ✅ St.spinner genérico | Considerar skeleton loader |
| Tabela de preços | ✅ Sort, filter nativo | ✅ Hover row | ✅ column_config padronizado | ✅ 10 colunas configuradas | R$/kg, R$/un, marca, promoção |
| Coluna "Frescor" | ✅ Badge freshness | ✅ Cores success/warning/danger | ✅ cd-badge classes | ✅ Baseado em days desde coleta | ✅≤7d, 8-30d, >30d |
| query_params (persistência) | ✅ Manter filtros | ✅ Atualização | ✅ label-visibility="collapsed" | ✅ Atualização via URL | ingrediente, store, tier |

### 7. Histórico (historico.py)

| Elemento | Funcionalidade | Estados | Acessibilidade | Feedback | Observação |
|----------|---------------|---------|----------------|----------|------------|
| Selectbox "Ingrediente" | ✅ Selecionar ingrediente | ✅ Hover | ✅ Label "Ingrediente" | ✅ Popula de DB | 23 ingredientes ativos |
| Selectbox "Período" | ✅ Selecionar dias | ✅ Hover | ✅ Label "Período" | ✅ [7, 15, 30, 60, 90, 180, 365] | Padrão: 90 dias |
| Checkbox "Apenas preços válidos" | ✅ Filtrar preços | ✅ Hover | ✅ Label "Apenas preços válidos" | ✅ Atualização em tempo real | valid_only flag |
| Selectbox "Tipo de Gráfico" | ✅ Mudar tipo de gráfico | ✅ Hover | ✅ Label "Tipo de Gráfico" | ✅ [Linha, Área, Barras, Dispersão] | 4 tipos plotly |
| 4 tipos de gráfico (linha/área/barras/dispersão) | ✅ Renderizar gráfico | ✅ Hover tooltip | ✅ Reduce motion respectado | ✅ Altura fixa 500px | Usa plotly.express |
| Tabela estatísticas por loja | ✅ Display estatísticas | ✅ Hover row | ✅ Contraste adequado | ✅ Ordenado por média | Média, mínimo, máximo, desvio, contagem |
| Tabela detalhamento | ✅ Tabela de registros | ✅ Sort, filter | ✅ column_config | ✅ 10 colunas configuradas | Inclui collected_at |
| Info "Total de registros" | ✅ Display informativo | ✅ st.info | ✅ Contraste adequado | ✅ Baseado em len(df) | Número de registros |

---

## Resumo Geral da Auditoria Funcional

| Área | Status Geral | Principais Problemas | Prioridade |
|------|-------------|---------------------|------------|
| Funcionalidade | ✅ 7/7 páginas operacionais | Alguns bulk actions em casos edge case | Alta |
| Estados (hover/focus/active) | ✅ 6/7 | Foco visível consistente | Média |
| Acessibilidade | ✅ 5/7 | ARIA labels em components customizados | Média |
| Feedback ao usuário | ✅ 7/7 | Alguns st.spinner genéricos | Baixa |
| Consistência | ✅ 7/7 | Design system consistente | Alta |
| Loading indicators | ⚠️ 3/7 | Alguns usam st.spinner em vez de skeleton | Baixa (melhoria) |

---

## Próximos Passos da Fase 4

1. Documentar todos os ✅/❌/⚠️ em FUNC_AUDIT_MATRIX.md
2. Aplicar fixes triviais imediatamente (ex: labels missing)
3. Registrar bugs complexos para Fase 7/8 (modernizações)
4. Validar fixes após aplicação
5. Passar para Fase 5 (Usabilidade & Consistência Visual)