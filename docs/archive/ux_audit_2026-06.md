# UX Audit — CustoDoce Dashboard
> Última revisão: 2026-07-05 13:04 UTC

> Gerado em: 19/06/2026  
> Escopo: `admin/app.py` (2843 linhas, 18 abas)  
> Metodologia: Revisão manual de código + varredura automatizada

---

## Histórico

- **Fase 10 (jun/2026)**: Auditoria original identificou **32 issues** (6 críticas + várias high/medium/low)
- **Commit `c93d303`**: 10 corrigidas (7 críticas + 3 high)
- **Auditoria atual**: 27 issues identificadas restantes (6 críticas, 9 high, 8 medium, 4 low)

---

## Issues CRÍTICAS (6)

| # | Local | Descrição | Sugestão |
|---|-------|-----------|----------|
| C1 | L2240-2251, L2343-2354 | **Exclusão sem confirmação real** — botão "Excluir" alterna para "Confirmar?" via flag de estado, sem popover ou diálogo. Usuário pode clicar duas vezes sem querer. | Substituir por `st.dialog("Confirmar exclusão?")` com botões "Sim" / "Cancelar". |
| C2 | L1480, L2221 | **Ações destrutivas sem confirmação** — "Forçar Coleta Agora" e "Executar" disparam workflows no GitHub Actions sem perguntar. | Adicionar `st.popover` confirmando antes do disparo. |
| C3 | L1077, L1386 | **Sobrescrita de arquivo sem backup visível** — `_render_schedule_info()` e `_render_selector_editor()` salvam scrape.yml e stores.yaml sem aviso. | Mostrar diff ou mensagem de backup antes de salvar. |
| C4 | L1621-1642 | **Email enviado sem preview** — "Enviar Relatório Agora" dispara imediatamente sem mostrar destinatário ou confirmar. | Adicionar `st.dialog("Confirmar envio")` com destinatário e assunto. |
| C5 | L743-794 | **Fluxo de aprovação confuso** — Aprovar item lê selectbox que renderiza *depois* do botão. Primeira execução falha. | Mover selectbox para antes do botão, ou desabilitar botão com `disabled=not selected`. |
| C6 | L1883-1949 | **Salvar por grupo perde edições** — Cada grupo tem seu próprio "Salvar" que reescreve todo `.env`. Se usuário edita grupo A e B mas só salva A, alterações em B são perdidas. | Botão único "Salvar todas" ao final, ou salvar todos grupos em qualquer clique. |

---

## Issues HIGH (9)

| # | Local | Descrição | Sugestão |
|---|-------|-----------|----------|
| H1 | L152-153, L1169, L1466 | **Silent `except Exception: pass`** — 3 locais engolem erro sem feedback. | Logar erro + `st.caption()` ou `st.toast()` com mensagem. |
| H2 | L365-366, L514-515, L604-607, L1172-1180, L1506-1516 | **Missing loading states** — Abas fazem chamadas DB/API sem `st.spinner`. Usuário vê tela congelada por 1-5s. | Envolver em `with st.spinner("Carregando...")`. |
| H3 | L214-216, L220-228, L236-238 | **DataFrames vazios exibidos sem fallback** — `_render_latest_prices()` mostra tabela em branco se vazia. `_render_boxplot()` retorna sem mensagem. | Adicionar `if df.empty: st.caption("Nenhum dado disponível.")`. |
| H4 | L170-176, L199-206, L620-627, L1136-1157 | **KPIs quebram no mobile** — 4 KPIs lado a lado em 375px é ilegível. | Reduzir para 2 KPIs por linha no mobile. |
| H5 | L353-363 | **Coluna vazia desperdiçada** — `st.columns(4)` com `with col4: pass`. | Usar `st.columns(3)` ou preencher 4ª coluna. |
| H6 | L2180, L2269, L2314, L2363 | **Mensagens de vazio inconsistentes** — Mistura de `st.info()`, `info_box()`, `st.caption()`, `st.warning()`. | Padronizar em `info_box()`. |
| H7 | L1257-1261, L186-196, L521, L613, L2528 | **Timezone misturado** — `datetime.utcnow()` (naive) vs `utc=True`. Cálculos errados perto de DST. | Padronizar em `pd.Timestamp.utcnow()` e manter timezone-aware. |
| H8 | L2278-2279 | **Input de UUID manual** — Formulário pede UUID da loja digitado. Ninguém sabe UUIDs. | Substituir por `st.selectbox()` com `get_all_stores()`. |
| H9 | L1876-1881 | **Edições salvas só no arquivo, não em memória** — `.env` é atualizado mas `os.environ` não. Usuário precisa reiniciar. | Adicionar `os.environ[key]=new_val` ou aviso "Válido após reinício". |

---

## Issues MEDIUM (8)

| # | Local | Descrição | Sugestão |
|---|-------|-----------|----------|
| M1 | L885, L1047, L1078, L1088, L1297, L1459, L1486, L2197, L2224, L2382, L2657 | **`import` dentro de funções** — 11 locais com import inline (json, re, httpx, shutil, statistics). ~50-100ms overhead cada. | Mover todos para topo do arquivo. |
| M2 | L781-794 | **Label oculta para acessibilidade** — `label_visibility="collapsed"` sem agrupamento visível. Leitores de tela podem perder. | Usar `label_visibility="visible"` com labels curtas. |
| M3 | L1050-1058 | **Cards HTML sem foco por teclado** — Componentes HTML não recebem foco Tab. | Adicionar `tabindex="0" role="region"`. |
| M4 | L1627-1642 | **Botão condicional sem explicação** — "Enviar Relatório" só aparece se SMTP configurado. Desaparece sem aviso. | Mostrar desabilitado com tooltip "Configure SMTP nas secrets". |
| M5 | L481-490, L573-591 | **Export condicional sem explicação** — CSV export some se `features.export.csv_enabled=false`. | Mostrar desabilitado com tooltip. |
| M6 | L1720-1732, L1762-1768 | **Campos sem agrupamento visível** — Múltiplos `label_visibility="collapsed"` sem fieldset. | Adicionar `st.markdown()` descritivo acima. |
| M7 | L2316-2394 | **JSON sem validação inline** — `condition` textarea espera JSON, erro só aparece no submit. | Adicionar `st.caption` preview do JSON parseado. |
| M8 | L867-868 | **Label de campo confuso** — "API Endpoint (VTEX)" não deixa claro o formato esperado. | Adicionar placeholder com exemplo. |

---

## Issues LOW (4)

| # | Local | Descrição | Sugestão |
|---|-------|-----------|----------|
| L1 | L69-77 | **Aviso de senha gerada visível a todos** — `st.warning` sobre `ADMIN_PASSWORD` aparece até na tela de login. | Mostrar só após autenticação. |
| L2 | L135-138 | **`_sanitize` importa `html` já importado** — Redundante, não quebra nada. | Usar `html` do import topo. |
| L3 | L363, L1619 | **Colunas vazias** — `with col4: pass` sem comentário. Espaço morto. | Remover ou comentar `# reservado`. |
| L4 | L598-600 | **Mapa de status com chave duplicada** — `"done"` e `"processed"` mapeiam pro mesmo valor. Frágil. | Normalizar antes do lookup. |

---

## Resumo

| Severidade | Quantidade | Principais Categorias |
|------------|-----------|-----------------------|
| Crítica | 6 | Ações destrutivas sem confirmação, fluxo de aprovação quebrado, perda de dados ao salvar |
| High | 9 | Erros silenciosos, falta de loading, responsivo quebrado, timezone inconsistente |
| Medium | 8 | Imports inline, acessibilidade, botões condicionais sem explicação |
| Low | 4 | Aviso de senha público, colunas vazias, redundância |

**Total: 27 issues** (além das 10 já corrigidas no commit c93d303)
