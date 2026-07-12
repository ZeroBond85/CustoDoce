# Lições Aprendidas
> Última atualização: 2026-07-12 12:00 UTC

> Extraídas de AGENTS.md. Numeração original preservada.
> Regras de execução/ambiente → `REGRAS.md`.

## Template de Lição RPR (Regra #11)

Toda nova lição extraída de falha no CI usa este template:

```markdown
### N. <Título curto>

- **Data + commit**: YYYY-MM-DD (sha123)
- **Sintoma**: <1-3 linhas do erro exato do CI>
- **Causa raiz**: <arquivo:linha + por que aconteceu>
- **Correção**: <arquivo:linha + diff resumido>
- **Teste de regressão**: <arquivo + nome do teste>
```

**Exceções ao template completo** (apenas bullet "Causa raiz" + "Correção"):
- Timeout/flakiness de rede
- Outage de infra externa (GitHub, Supabase)
- Mudança em `workflows/*.yml` (RPR simplificado)

---

### 44. CI integration tests skipados sem motivo (auto-skip exigia `SUPABASE_DB_PASSWORD`)

- **Data + commit**: 2026-07-09
- **Sintoma**: `integration` job em `ci.yml` reportava `112 skipped in 0.76s`. Auto-skip silencioso, zero indicação de razão.
- **Causa raiz**: `tests/conftest.py:_has_real_db()` linha 33 exigia `SUPABASE_DB_PASSWORD` (legado psycopg2/porta 5432). Mas AGENTS.md regra #3 proibe `psycopg2` (CI bloqueia porta 5432) — somente `exec_sql_query` RPC porta 443 é usada. Os jobs CI passam `SUPABASE_URL`/`SUPABASE_ANON_KEY`/`SUPABASE_SERVICE_ROLE_KEY` mas **nunca** `SUPABASE_DB_PASSWORD`, então todos os 112 testes de integration eram pulados.
- **Correção**: `_has_real_db()` em `tests/conftest.py:30` agora exige `SUPABASE_URL` + (`SUPABASE_SERVICE_ROLE_KEY` OU `SUPABASE_ANON_KEY`), não mais `SUPABASE_DB_PASSWORD`. Docstring cita a regra #3.
- **Teste de regressão**: `tests/unit/test_conftest_missing_creds.py` (5 cenários: vazio, só service_role, só anon, só legacy db_password, URL inválida).



### 1. Mocks — boundary layer, not internal functions

```python
# ❌ ERRADO: patcha onde a função é definida
@patch("services.dashboard_queries.get_latest_prices_cached")
def test_x(): ...

# ✅ CERTO: patcha onde é usada
@patch("dashboard.pages.relatorios.get_latest_prices_cached")
def test_x(): ...
```

Ou marca como `@pytest.mark.integration` e deixa o conftest `db_conn` resolver via RPC.

### 2. Tests que tocam Supabase real — marque `integration`

Marque com `@pytest.mark.integration`. `pyproject.toml` tem `addopts = "-m 'not slow and not integration'"`.

### 3. `exec_sql_query` RPC (porta 443), NUNCA `psycopg2` (porta 5432)

GitHub Actions bloqueia porta 5432. Use o fixture `db_conn` do `tests/conftest.py`.

### 4. Cleanup POST test, não só PRE

Setup PRE não basta — sempre cleanup POST também. Filtre por `collected_at = today` ao validar.

### 5. `deploy_check.py` — required vs optional env

Required: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. Optional: `GMAIL_*`, `AUTH_SECRET_KEY`, `SUPABASE_ANON_KEY`, `TELEGRAM_*`. Opcionais viram WARN, não bloqueiam.

### 6. Pre-commit hook SECRETS GUARD — bloqueia, não skipa

Padrões: `sk-*`, `gsk_*`, `sk-or-*`, `sk-or-v1-*`, `sk-proj-*`, `hf_*`, `github_pat_*`, `nvapi-*`, `mOns*`, `AQ.*`.

### 7. `PIP_INDEX_URL` → `PIP_EXTRA_INDEX_URL`

Para torch CPU em CI: use `PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu`. `PIP_INDEX_URL` SUBSTITUI PyPI e quebra `ruff`/`mypy`.

### 8. `get_supabase()` deve ter fallback se `SUPABASE_ANON_KEY` faltar

```python
# ✅ CERTO:
key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
```

`get_supabase()` prefere `SUPABASE_ANON_KEY` mas aceita `SUPABASE_SERVICE_ROLE_KEY` como fallback.

### 9. `SUPABASE_ANON_KEY` deve ser passado explicitamente nos jobs CI

A secret existe no GitHub mas precisa ser mapeada no workflow. Sempre adicionar `SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_ANON_KEY }}`.

### 10. `exec_sql_query` RPC — sem trailing semicolons

SQL com `;` no final quebra a subquery. Remova qualquer `;` no final de queries enviadas via `client.rpc("exec_sql_query", {"sql": sql})`.

### 12. Streamlit Cloud E2E flakiness — use continue-on-error + warmup agressivo

E2E contra infra externa que hiberna = sempre continue-on-error + warmup agressivo (min 6 rounds, 3min total). Verificar Lição #18 (failure() com continue-on-error).

### 14. Auto-disable scrapers — SEMPRE investigar causa raiz antes

Antes de mexer em `is_active`, fazer dry-run do `_auto_disable_if_needed`. Logs devem mostrar CAUSA detalhada.

### 15. Self-healing OBRIGATORIO em todos os scrapers

API obrigatória:
- `record_failure(scraper_name, reason, items_found, products_matched, flyer_count, attempted_by)`
- `record_success(scraper_name, items_found, products_matched, flyer_count, attempted_by)`
- `attempt_heal(scraper_name=None, dry_run=False)` — cron 15d

Config em `config/features.yaml`:
```yaml
self_healing:
  enabled: true
  required: true
  threshold_failures: 3
  heal_days: 15
  recovery_min_items: 1
```

### 16. Causa raiz > Mascarar

Investigar raiz ANTES de aplicar patches. Logar `error_class` (Timeout|SSLError|LayoutChanged|...). Causa raiz ≠ log.message.

### 17. `hashFiles()` no GHA só funciona com arquivos trackados pelo git

```yaml
# ✅ CERTO:
if: steps.file.outputs.filename != ''
```

### 18. `if: failure()` não dispara dentro de `continue-on-error: true` jobs

Use `if: always() && steps.meu_teste.outcome == 'failure'` e adicione `id:` ao step.

### 19. Script inline Python em heredoc no YAML — delimiter na coluna 0

Solução: extrair para arquivo `.py` separado.

### 20. Streamlit Cloud virou SPA (React) — HTTP warmup é inútil

Playwright (browser real) é obrigatório. CI (push/PR) usa localhost:8501. Schedule mensal testa cloud real.

### 21. `page.wait_for_timeout()` é frágil para cold start E2E — use polling

Sempre usar polling (45s) para elementos que dependem de renderização assíncrona.

### 22. `httpx>=0.28` pode resolver para 1.x — sempre pin upper bound

```txt
# ✅ CERTO:
httpx>=0.28,<1.0
```

### 24. "Pré-existente" não é desculpa — corrija ou prove que é bloqueado

"Pré-existente" exige prova. Se é 1-5 linhas e não quebra nada, corrija agora.

### 23. Migration SQL nova precisa ser incluída em `deploy_database.py`

Toda migration SQL nova DEVE ser adicionada ao `generate_consolidated()`.

### 25. Novo código = novos testes

Módulo novo = `test_<modulo>.py` no mesmo PR. Unitários puros primeiro (mock I/O), integração depois.

### 26. Push → Acompanha CI até PASS

Análise prévia → resiliência durante → completude no fim. `--no-verify` só em emergência real, com justificativa no commit.

### 29. Sidebar/navigation NÃO renderizava em headless por TypeError/AttributeError silencioso

Root cause: `get_longitudinal_winners()` sem argumento `days` + `normalized` bool em vez de dict. Fix: `days=90` + `isinstance` guard.

### 30. Normalized pode ser `true` (bool) no Supabase — NUNCA use `p.get("normalized") or {}`

Commit: `da3e9f6`. SEMPRE proteger com `isinstance(raw, dict)` antes de `.get("price_per_kg")`. 21 ocorrências em 7 arquivos.

### 31. Schema Sync Validation — pre-req obrigatório antes de push

3 camadas: Contract tests (`test_dashboard_query_shapes.py`) + Schema introspection (pre-push) + Mocks realistas (dump real).

### 32. Mocks devem refletir realidade — gerar de dump real, não hand-crafted

Fixtures de teste = dump real do Supabase. Se mock precisa de caso edge, adicionar explicitamente ao fixture real, não inventar.

### 33. Contract tests como primeira linha de defesa — não E2E

Novo query em `dashboard_queries.py` = novo teste em `test_dashboard_query_shapes.py` no MESMO PR. E2E é validação de UX, não de schema.

### 34. CI leve para iteração E2E — não queimar free tier no pipeline completo

Iteração de bug E2E = branch + `ci-e2e-only.yml` (~4 min). Full CI só no merge final.

### 35. AGENTS.md sanitization (Sprint 11) — schema, split, agents_tool.py

AGENTS.md cresceu para 974 linhas, misturando lições, regras infra, ambiente e projeto vivo. Split em 3 arquivos + schema YAML + ferramenta de gestão:

- `config/agents_schema.yaml` — schema que define o que pode entrar no AGENTS.md (headings, max_lines, blocked patterns)
- `scripts/agents_tool.py` — ponto único de entrada: `--check`, `--full`, `--add-rule`, `--add-lesson`, `--status`
- 3 gatilhos de validação: pre-commit (+1s se AGENTS.md staged) → pre-push (+1s, agents_tool --check) → CI docs-sync (+8s)

Regra permanente:
- AGENTS.md mantido em ~350 linhas máximo
- Lições novas vão para LESSONS.md (via `--add-lesson`)
- Regras novas de execução vão para REGRAS.md
- CI valida schema a cada push/merge

### 36. Lesson #33

30 bugs de schema mismatch encontrados na auditoria manual de 19 páginas do dashboard contra information_schema real do Supabase. Todo dict key access em páginas Streamlit deve ser validado contra schema real (SELECT column_name FROM information_schema.columns WHERE table_name=...). Mocks de teste DEVEM refletir schema real — nunca hand-crafted com keys imaginarias.

### 37. Drift skills ↔ docs ↔ disco é recorrente — SST operacional

**Causa raiz:** `sync_docs.py` detectava drift numérico (test counts, pages) mas nunca inspecionava `.opencode/skills/`. Skills podiam ser adicionadas/removidas sem qualquer falha em CI. Três verdades conflitavam: disco, `APPROVED_SKILLS` (hardcoded), e docs.

**Solução aplicada:**
- SST = disco (`.opencode/skills/`) + `APPROVED_SKILLS` + `docs/skills.md` (auto-gerado)
- `sync_docs.py` agora varre skills: `_check_skills_sync()` detecta disco ≠ approved ≠ docs
- `_sync_skills_md()` regenera `docs/skills.md` a partir do disco + categorias
- pre-commit Layer 6: bloqueia se skills mudarem sem `docs/skills.md`
- CI docs-sync job: `sync_docs --check --strict --experimental` falha se drift

**Regra permanente:** Toda skill nova = SST em 3 lugares verificáveis. `sync_docs --check` é o portão. Não editar `docs/skills.md` manualmente.

### 38. Dependency drift recorrente — auditoria automatizada obrigatória

**Causa raiz:** O projeto tinha `pip-audit --strict` no `ci.yml:lint` (linha 33), mas cobria apenas `requirements.txt` (prod). CVEs em deps de teste/dev (`diskcache 5.6.3`, `pytest 8.3.3`) só eram descobertas em scans manuais. E o time não tinha como **descobrir** novas vulns automaticamente após release.

**Solução aplicada:**
1. **Higienização**: deps transitivas (`numpy`, `transformers`, `pillow`, `joblib`) declaradas explicitamente em `requirements.txt`. `psycopg2-binary` movido de dev → prod (scripts de deploy precisam dele).
2. **Vulnerabilidades**: `pytest` 8.3.3 → 9.0.3 (CVE-2025-71176 corrigida), `pytest-asyncio` 0.24 → 1.4.0 (compat com pytest 9.x). `diskcache` aceito em dev (Sprint 12 policy — FP transitivo).
3. **Automação**: novo workflow `.github/workflows/dependency-audit.yml`:
   - `audit-prod` job: bloqueia PR se `pip-audit --strict -r requirements.txt` falhar
   - `audit-dev` job: informational (continua em erro, registra em log)
   - `full-scan` job: roda deptry + pip-licenses mensalmente (cron dia 1, 9am UTC)
4. **Lock sync**: `pip-compile` regenera `requirements.lock` sempre que PR alterar requirements.

**Regra permanente:**
- Toda mudança em qualquer `requirements*.txt` → regenerar `requirements.lock` via `pip-compile`
- `pip-audit --strict -s osv -r requirements.txt` é o portão de release (já existente, mantido)
- CVEs Critical/High em prod = bloqueia release sem exceção
- CVEs Medium/Low em dev/test = aceitas até próximo sprint (documentar em `docs/security.md`)
- Falsos positivos do `deptry` (transitivas reais): NUNCA remover sem grep `import <pkg>` em todo o codebase

### 33. Sprint 13 — Saneamento de working tree com `scripts/sanitize.py`

**Problema:** 1.5GB de resíduo acumulado no working tree (caches Python, wheels baixados manualmente, resíduo do installer miniconda, modelo ONNX de 465MB, artefatos de skills audit, 12 arquivos apátridas commitados).

**Solução aplicada:**
1. **Script de saneamento**: `scripts/sanitize.py` — 10 categorias modulares com dry-run por default, snapshot+rollback, lockfile cooperativo, exclusão de `.venv314`/`.git`.
2. **.gitignore consolidado**: regras cobertas para `C?Usersericsf/`, `CustoDoce.7z`, `docs/skills.md`, `data/audit/`, `data/skills_backup/`, `.archive/`. Override `!.opencode/skills/**` para forçar versionamento das 33 skills.
3. **Pre-commit RESIDUE GUARD**: 7ª camada do hook — bloqueia commit com `.whl`, `miniconda.sh`, `C?Usersericsf/`, apátridas, `data/audit/`, `data/skills_backup/`, `skills-lock.json`, `.archive/sanitize/`.
4. **Skills versionadas**: todas as 33 skills (incluindo theme-factory/themes, extras) forçadas no repo via `git add -f`.

**Regra permanente:**
- `python scripts/sanitize.py --execute --quick` ao final do dia (ou antes de commits grandes)
- `python scripts/sanitize.py --dry-run` semanalmente (segunda) para auditoria
- Hook RESIDUE GUARD bloqueia commit acidental de resíduo — `--no-verify` é bypass de emergência
- `scripts/sanitize.py --rollback` reverte o último `--execute` via snapshot em `.archive/sanitize/`

### 36. CI status check antes de push — pipeline verde ou bloqueia

Antes de qualquer push para `master`, verificar se o CI está verde. O pre-push hook step [0/5] faz essa checagem automaticamente:
- CI verde → OK, prossegue
- CI vermelho → **AVISO OBRIGATÓRIO** (não bloqueia — paradoxo: pode ser o fix que vai tornar o CI verde)
- `gh` não autenticado → **AVISO** para configurar

Ordem: primeiro verificar CI, depois executar os demais steps locais.

Autenticação: `gh auth login` ou `GH_TOKEN` no `.env`. Responsabilidade do desenvolvedor de não pushar sobre CI vermelho a menos que seja a correção.

### 39. Monitoração é essencial — se não é monitorado, assuma que está quebrado

**Causa raiz:** Phase 0 security baseline descobriu 6 RLS policies inseguras, 3 RPCs `SECURITY DEFINER` sem `REVOKE`, fallback silencioso de `get_service_client()`, admin app gerando senha aleatória invisível, e JWT morto — tudo passando despercebido por meses porque **não havia monitoração em nenhum desses pontos**.

Toda mitigação foi reativa. Com monitoração, teriam sido descobertas proativamente semanas antes.

**Abrangência (monitore tudo que pode falhar silenciosamente):**

| Domínio | O que monitorar | Como |
|---------|----------------|------|
| Segurança | RLS policies, permissões de funções, tentativas de auth falhas | `db_security_lint.py` + Supabase audit log |
| Scrapers | Failure rate, circuit breaker, auto-disable | `scraper_health.py` + `heal-scrapers.yml` |
| CI/CD | Pass/fail rate, duração, timeout | `git pw` com `gh run watch` |
| Database | Migration drift, schema changes, query perf | `validate_db_schema.py` + cron |
| Dependências | CVEs em prod e dev, licenças | `dependency-audit.yml` (mensal) |
| Código morto | Funções/classes não utilizadas | `vulture` (mensal) |
| Secrets | Exposição acidental em working tree | `detect-secrets` (pre-commit) |
| Free tier budget | GHA minutos, Supabase storage, Streamlit horas | Alerta manual por email |

**Regra permanente:**
- Toda nova funcionalidade DEVE incluir pelo menos um ponto de observabilidade (log estruturado, métrica, alerta)
- Nada que pode falhar silenciosamente deve ficar sem monitoração por mais de um sprint
- `git pw` (CI watch) é obrigatório para todo push — não monitorar CI é aceitar merge silencioso de breaking change
- Se um componente quebrou e ninguém percebeu, a culpa não é do componente — é da falta de monitoração

### 42. Monitoração de CI em shells com timeout (Polling vs Watch)
  
 **Causa raiz:** O comando `gh run watch` mantém uma conexão aberta e aguarda a conclusão do run. Em ambientes de shell com timeout estrito (ex: 120s), o comando é interrompido prematuramente, impedindo o acompanhamento do CI até o fim.
  
 **Solução:** Substituir o "Watch" por "Polling" (consultas repetidas e curtas).
  
 **Técnica de Polling:**
 `gh run view <run_id> --json conclusion --jq '.conclusion'`
  
 **Regra permanente:** Agentes devem implementar loops de polling com intervalos (ex: 30s) para monitorar a conclusão do CI, evitando a dependência de comandos de watch de longa duração.
 
### 43. Scheduled workflows não devem usar GH_PAT custom token no Checkout
**Causa raiz:** No run https://github.com/ZeroBond85/CustoDoce/actions/runs/28803088935 (scheduled, master), o Checkout falhou 3× com `fatal: could not read Username for 'https://github.com': terminal prompts disabled` porque `with: token: ${{ secrets.GH_PAT }}` força prompt interativo ausente em modo scheduled; e o `python -c "import httpx"` nos alertas de commit/e-mail também quebrou (provavelmente por ambiente restrito).
**Solução:** Remover `with: token:` do step "Checkout" em `.github/workflows/scrape.yml` (mantido o default); substituir `python -c "import httpx"` por `curl -X POST` direto nos passos "Alert on commit failure" e "Alert on email failure"; GH_PAT preservado apenas no step "Commit Latest Pushing latest prices" (git push).
**Validação:** Run https://github.com/ZeroBond85/CustoDoce/actions/runs/28803210736 (on_demand_scrape.yml, scheduled) rodou verde com checkout sem token. Novo teste unitário `tests/unit/test_scrape_workflow.py` garantindo que `.github/workflows/scrape.yml` NÃO contém `token: ${{ secrets.GH_PAT` no step de checkout.
**Data:** 2026-07-06



### 44. GH Actions Step Validation

Steps sem 'run:' ou 'uses:' geram 'failure' com 0 jobs. yaml.safe_load nao detecta. Validar com test_all_steps_have_run_or_uses() antes de push.

### 45. git_push.py timeout — Polling obrigatório para CI Watch em shells com timeout

**Causa raiz:** O script `scripts/git_push.py` usa `gh run watch --exit-status` (linha 136-141) que mantém conexão aberta até o CI completar. Em shells com timeout estrito (ex: 120s padrão), o comando é interrompido prematuramente, perdendo o status final do CI (success/failure) e impedindo o auto-retry.

**Solução:** Substituir `gh run watch` por polling assíncrono com `gh run view <run_id> --json conclusion` em loop (intervalo 30s) — igual à técnica da Lição #42. O timeout do subprocesso deve ser `CI_WATCH_TIMEOUT` (padrão 600s), não o timeout do shell.

**Regra permanente:** 
- `git_push.py` DEVE implementar polling, não `gh run watch`
- Todo agente que monitorar CI deve usar polling repetitivo até conclusão final
- Se shell timeout < tempo do CI, o watch falha e perde a conclusão

### 46. Serviços com dependências opcionais — retorne False, não levante exceção

**Causa raiz:** `services/telegram_service.py::send_telegram_message()` levantava `ValueError("TELEGRAM_TOKEN must be set")` quando o token não estava configurado. Isso propagava como `logger.error` no `main.py`, poluindo logs de CI com falsos positivos (exit code 0, mas parecia erro).

A mesma regra vale para `send_email()` em `email_service.py` — levantava `ValueError` sem SMTP configurado.

**Solução:**
- `send_telegram_message` retorna `False` (não raise) quando token faltando
- `alert_service.py::process_proactive_alerts()` envolve notificações em `try/except` com logger.warning
- O import ausente `send_email_notification` foi resolvido com alias: `from services.email_service import send_email as send_email_notification`

**Regra permanente:**
- Serviços com dependências opcionais (Telegram, SMTP, etc.) NUNCA devem levantar exceção por config faltante — retornar `False` ou `None`
- Quem chama deve tratar falha de notificação como warning, não erro
- O `main.py` não deve logar como `logger.error` falhas de notificação

### 47. Scripts referenciados em workflows devem ter test de existência

**Causa raiz:** `scripts/enrich_prices.py` estava referenciado em `.github/workflows/scrape-reusable.yml` mas o arquivo nunca existiu no repositório. A CI rodou 3 vezes (`enrich` job fail) até o script ser criado.

**Solução:** Criar `scripts/enrich_prices.py` + adicionar `test_enrich_prices_script_exists()` em `test_ci_infrastructure.py`.

**Regra permanente:** TODO script referenciado em qualquer workflow YAML deve ter um test de existência correspondente em `tests/unit/test_ci_infrastructure.py`.

### 48. `pip-audit --strict` NÃO significa "falha em vulnerabilidades"

**Causa raiz:** Workflow `ci.yml` usava `pip-audit --strict -s osv -r requirements.txt` no step "Audit dependencies". O flag `--strict` no pip-audit 2.x significa **"falha se a COLETA de dependências falhar"** (não "falha em vulns"). Em CI (ubuntu/Py3.14) a coleta de alguma dependência de `requirements.txt` falha → exit 1 mesmo com "No known vulnerabilities found". Combinado com `set -e` implícito do GitHub Actions, o script morria antes do check de severidade.

**Solução:** Remover `--strict` (pip-audit falha por padrão em vulns reais) + capturar exit code explicitamente (`set +e` / `set -e`) para não abortar o script. Bloquear só em HIGH/CRITICAL via grep de `Severity:`.

**Regra permanente:**
- Nunca usar `pip-audit --strict` para "falhar em vulnerabilidades" — esse é o comportamento DEFAULT
- `--strict` = falha em erro de COLETA de dependência (falso positivo em ambientes com extra-index-url, Py3.14, etc.)
- Em workflows, sempre capturar exit code de pip-audit explicitamente (`set +e` antes, `set -e` depois) para o check de severidade rodar

### 49. Falha de CI pré-existente = GAP de teste, tratar imediatamente

**Causa raiz:** O pre-push hook avisou "CI está vermelho" (master com F401 em `test_alert_service.py`/`test_telegram_service.py` + pip-audit bug). O agente tratou como "não são nossas mudanças, fora de escopo" e seguiu. Isso viola AGENTS.md regra #11 ("Falha no CI = Gap de Teste... 'Tentar de novo' é proibido").

**Solução:** Reproduzir a falha de CI localmente (`gh run view <id> --log-failed`), corrigir na branch feature (rebase onto origin/master + fix), e registrar LESSONS.md. No caso: F401 `import pytest` não usado (removido) + pip-audit `--strict` (removido).

**Regra permanente:**
- Se o pre-push avisa "CI vermelho", NÃO é desculpa para ignorar — investigar e corrigir
- Falha de CI pré-existente continua sendo GAP de teste se não for tratada antes do merge
- Sempre reproduzir localmente + corrigir + LESSONS.md (mesmo que o bug não venha das nossas mudanças)


### 50. E2E real/interactions: login exige usuario E senha; sidebar usa <a> (st.navigation)

**Causa raiz:** Os testes E2E (`tests/e2e/test_e2e_real.py`, `tests/e2e/conftest.py`) falhavam em massa porque o fluxo de login so preenchia `input[type=password]` e NAO o campo "Usuario". O `dashboard/login_page.py` exige `username AND password` nao-vazios (`login_page.py:161-167`); sem usuario o login falha, o `st.navigation()` nunca renderiza a sidebar (`admin/app.py:120-128` faz `st.stop()`), e entao:
- `e2e-interactions` dava `pytest.skip` em todas as 19 abas (nav link nao encontrado)
- `e2e-real` dava `pytest.fail("Nav item nao encontrado na sidebar")` nas 4 primeiras abas
A segunda causa: `check_for_errors` (`test_e2e_real.py`) usava substrings soltas (`text=column`, `text=does not exist`, `text=Error:`) que dao FALSO-POSITIVO em texto legitimo. E `test_sidebar_completeness` comparava labels limpos de `MENU_GROUPS` com o texto da sidebar que vem COM emoji/icone prefixado (ex: "Precos") -> divergencia sempre.

**Solucao aplicada:**
- `_login_local` (conftest) e `login_to_app` (test_e2e_real) preenchem username "admin" + password + clicam Entrar.
- `logged_in_app_and_page` (test_e2e_real) tornou-se `scope="session"` (1 login por suite, nao por aba) -> cold-start cai de ~6min para ~80s.
- `check_for_errors` endurecido: so `.stException`, `.stAlert`, `Traceback`, regex ancorados (`^Error: `, `relation .* does not exist`, `column .* does not exist`). `page=` passado para salvar screenshot de evidencia.
- `test_sidebar_completeness` normaliza o texto da sidebar (remove emoji/icone do inicio ate a 1a letra) antes de comparar com `MENU_GROUPS`.
- Helpers de interacao (`_click_button`, `_click_tab`, etc.) so clicam se `is_visible()`; abas sem interacoes registradas viram PASS (navegou + sem erro), nao SKIP.

**Regra permanente:**
- E2E local (`e2e-full`) e nuvem (`visual`): o login SEMPRE precisa de usuario+senha; nunca preencher so a senha.
- Nunca usar `text=` substring solta em check_for_errors; usar seletores de erro real ou regex ancorado.
- Ao comparar labels da sidebar com `MENU_GROUPS`, normalizar emoji/icone prefixado.
- Fixtures de browser/login em E2E devem ser `scope="session"` para nao estourar tempo de cold-start.
- "Sem skip": nav ausente = `pytest.fail` com screenshot; pagina sem interacao = PASS. Skip so se for intencional (teste legado explicito).

### 52. Testes de conftest que carregam .env não isolam — monkeypatch `dotenv.load_dotenv` para no-op

- **Data + commit**: 2026-07-09 (sessão saneamento-fase-1 pré-tornar-público)
- **Sintoma**: `tests/unit/test_conftest_missing_creds.py::test_has_real_db_false_quando_env_vazio` (após reorganização do arquivo: `test_has_real_db_false_quando_env_minimo`) falhava intermitentemente em CI. `module._has_real_db() is False` falhava porque retornava `True`. Outros 4 cenários passavam.
- **Causa raiz**: `tests/conftest.py:23` chama `load_dotenv(Path(__file__).resolve().parent.parent / ".env")` **incondicionalmente no import do módulo**. Quando o teste carrega conftest em módulo isolado (`spec_from_file_location`) com `os.environ` limpo + `monkeypatch.delenv("SUPABASE_URL", raising=False)`, o `load_dotenv` é executado **DENTRO do `exec_module`** e **injeta o `.env` real do projeto** em `os.environ` ANTES do `delenv` aplicar (o `monkeypatch.delenv` foi feito antes do exec, mas o `load_dotenv` re-injeta durante o exec). Resultado: o módulo carregado tem `SUPABASE_URL` populada, `_has_real_db()` retorna True.
- **Correção**: Em `tests/unit/test_conftest_missing_creds.py` adicionei `monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)` **antes** do `spec.loader.exec_module(module)`. Assim o módulo carrega sem `load_dotenv` substituir nada em `os.environ`. 5/5 testes passam.
- **Teste de regressão**: Coberto pelos 5 cenários existentes `test_has_real_db_*` em `tests/unit/test_conftest_missing_creds.py` — sem o monkeypatch de `load_dotenv`, **nenhum** dos 5 passa de forma confiável quando existe `.env` no projeto (cenário local-dev).

**Regra permanente:**
- Ao testar módulos que chamam `load_dotenv(...)` no import, **sempre** monkeypatch `dotenv.load_dotenv` para no-op ANTES de `exec_module` em testes de isolamento.
- `monkeypatch.delenv` sozinho **não basta** se o módulo re-injeta valores durante import via `load_dotenv`.
- Alternativa: usar `load_dotenv(..., override=True)` no conftest para permitir que CI (env vars) sobreponha `.env` local — mas isso muda semântica do conftest em produção. Preferível patchar no teste.

### 52. sync_docs.py #sync# so rodava SÓ v2 #CURRENT blocks# # README/REGRAS/API/timestamps ficavam desatualizados no CI mesmo quando --sync era invocado

**Causa raiz:** Em , o branch  chamava apenas  (CURRENT blocks em docs arbitrários). Os updateers v1 , , ,  (timestamps) so eram chamados pela funcao , que era invocada apenas sem . Resultado: o CI rodava  (v2 só) e depois  falhava por drift no README/REGRAS/timestamps.

Além disso,  comparava  (regex "(\d+)\s+tests?\s+collected") com a contagem por regex de sync+async test classes. Como pytest moderno imprime "722 items collected" (nao "tests"), o regex capturava lixo ("6 tests collected" espalhado) e gerava drift falso.

E um terceiro bug menor:  suprime o markup /, entao o regex de contagem nao achava nada.

**Solucao:**
- :  agora chama primeiro  para v1 (README/REGRAS/AGENTS/API/timestamps), e só depois  para v2 (CURRENT blocks).
- : regex atualizado para  (alinhado com a saida real do pytest).
-  e : trocar  por  (preserva o markup ).
- : tolerância de ±5 entre  e  (pytest pode contar testes parametrizados indiretamente).

**Replicacao:** Rodar === v1 sync (README/REGRAS/AGENTS/API/timestamps) === localmente e validar com  # esperado "All docs in sync". Se drift em e2e/unit/scan persistir, este modelo se aplica.

**Regras permanentes:**
- Ao adicionar um novo flag ao , cobrir AMBAS as arvores v1 (updateers específicos por arquivo) e v2 (CURRENT blocks). Nunca passar so por uma.
- Drift threshold deve ter tolerância # parametrizacao ou duplicates counted pela runtime do pytest nao sao ausencia de testes.
- Regex precisa casar a saida literal do pytest # se mudou  para , atualizar.

---
## Lição 43: Auditoria profunda de testes (Fases 0-9) — 2026-07-11

**Sintoma:** Testes mortos, mocks subutilizados, gaps de cobertura, violações Regra #3, workflows inconsistentes.

**Causa:** Crescimento orgânico sem auditoria periódica. Dead code acumulou (sync_md_catchup.py, test_dashboard_full.py, test_brand_extractor.py, test_playwright_local.py, test_unit_extractor.py, deploy-staging.yml.disabled, scripts/archive/). Mocks centralizados em mock_data.py mas só 2/16 sets consumidos. Regra #3 (psycopg2/5432 proibido) violada em 10 arquivos integration. Workflows duplicados (ci-e2e-only.yml + teste_full_manual.yml) com e2e-full vazio.

**Correção (Fases 0-9):**
- Fases 1-3: Vacinas Regra #3 (8→0), pytest.ini→pyproject.toml, merge feature branch
- Fase 4: 6 mock consumers reais (23 testes) consumindo mock_data.py
- Fase 5: 41 testes unit para 7 services 0% coverage (store_registry, scraper_alert, review_queue, import, maintenance, price_intelligence, dashboard_queries, collector)
- Fase 6: extractor.py (7 testes), regressões 21f7155 (Extra/Pao date fix, 'pao-de-acucar', 'minuto' fallback), pao_flyer CAMPAIGN_TYPE='pao-de-acucar', docstring fix
- Fase 7: 14 testes para 5 pages (insights, capacity_planning, alertas, scraper_health, lojas_pendentes)
- Fase 8: 16 testes UI components (freshness, info_box, user_badge, inject_css, load_css, logo)
- Fase 9: vision_strategies (12 testes), flyer_scraper_extra_pao (9 testes), extractor (7 testes)

**Regras permanentes:**
- Auditoria trimestral: rodar `python -m pytest tests/unit/ --collect-only -q | wc -l` e comparar baseline.
- Testes mortos (>0 chamadores, skip permanente, ou duplicados) → remover em Fase 13.
- Mocks centrais → auditar consumo a cada sprint.

---
## Lição 44: .gitignore data/store_backups/ — 2026-07-11

**Sintoma:** 3 backups YAML idênticos (115KB) commitados em data/store_backups/ (commit 22fd346).

**Causa:** Script de backup (scripts/backup_stores_yaml.py) escreve em data/store_backups/ mas pasta não estava no .gitignore.

**Correção:** Adicionar `data/store_backups/` ao .gitignore (seção ML/model artifacts).

**Regra permanente:** Qualquer pasta que scripts escrevam automaticamente (backups, cache, dumps) → adicionar ao .gitignore ANTES do primeiro commit.

---
## Lição 45: Guard rule3_db_password — 2026-07-11

**Sintoma:** Regra #3 AGENTS.md (NUNCA psycopg2/5432, SOMENTE RPC 443) não era enforceada automaticamente.

**Correção:** Criar `tests/unit/test_rule3_db_password_guard.py` (AST check) que falha se algum teste usar SUPABASE_DB_PASSWORD.

**Regra permanente:** Guard AST em pre-commit/CI para anti-patterns críticos (senhas, portas proibidas, imports perigosos). Rodar em `ci.yml` job `lint`.

---
## Lição 46: Cleanup testes mortos — 2026-07-11

**Sintoma:** 5 arquivos testes mortos acumulados:
- test_sync_md_catchup.py + test_sync_md_catchup.py (script morto)
- test_brand_extractor.py (duplicado de test_services/test_brand.py)
- test_playwright_local.py (skip permanente)
- test_unit_extractor.py (10 testes p/ 18 LOC)
- deploy-staging.yml.disabled (workflow obsoleto)

**Correção:** Fase 13 — remover com `git rm` e atualizar .gitignore se necessário.

**Regra permanente:** Antes de adicionar teste novo, verificar se similar já existe. `git grep "test_" -- tests/` antes de criar.

## 47. AsyncMock.return_value padrão é AsyncMock, não MagicMock

**Sintoma:** `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` ao executar `test_collector_facebook.py::TestFacebookFlyerScraper::test_process_post_parses_products_from_image`.

**Causa:** `@patch("httpx.AsyncClient.get")` cria um `AsyncMock` (pois `AsyncClient.get` é corrotina). `AsyncMock.return_value` padrão é outro `AsyncMock`. O teste fazia `resp = await client.get(url)` → `resp = mock_get.return_value` (um `AsyncMock`). Atributos de `AsyncMock` retornam corrotinas, então `resp.raise_for_status()` retornava uma corrotina nunca aguardada.

**Correção:** Substituir:
```python
mock_get.return_value.__aenter__.return_value = mock_resp  # ❌
```
por:
```python
mock_get.return_value = mock_resp  # ✅
```
`mock_resp` é um `MagicMock` comum, então `raise_for_status()` é síncrono.

## 48. Marcador `slow` para documentação, não filtro automático

**Decisão:** `test_alert_service.py` (1 teste ~32s) marcado como `@pytest.mark.slow`. O `addopts` global **não** inclui `-m 'not slow'` para evitar quebrar workflows CI que rodam testes lentos (diagnostics, real, integration). O marcador serve como documentação e filtro opcional. Para pular testes lentos localmente: `pytest -m 'not slow'`.

## 49. CRLF root fix: `core.autocrlf = true` no Windows — WSL não precisa

**Sintoma:** Git emitia "CRLF will be replaced by LF" em todo `git add` de arquivos texto no Windows. Pre-commit Layer 8 bloqueava commits com CRLF. Tentativa de auto-fix no hook não resolvia a raiz — o warning continuava aparecendo.

**Causa raiz:** Windows usa `\r\n` nativamente. `core.autocrlf = false` + `.gitattributes eol=lf` faz Git detectar CRLF e avisar sobre a conversão no staging. O problema é intrínseco ao ecossistema Windows — no WSL (Linux) não existe CRLF, então o warning nunca aparece.

**Correção raiz:** `git config core.autocrlf true` (local ao repo):
- Git converte CRLF→LF no staging SILENCIOSAMENTE (sem warning)
- Git converte LF→CRLF no checkout (Windows espera CRLF)
- `.gitattributes` com `*.py eol=lf` etc. continua valendo — arquivos específicos mantêm LF puro
- O warning "CRLF will be replaced by LF" desaparece porque `autocrlf=true` diz ao Git "sim, eu sei que tem CRLF, converte sem avisar"

**Regra permanente (NOVO TOP 10 REGRA #14):**
- Windows: `core.autocrlf = true` OBRIGATÓRIO no repo. O pre-commit hook verifica e falha se estiver `false` ou `input`.
- WSL: `core.autocrlf` deve ser `false` ou `input` (Linux não usa CRLF).
- `.gitattributes` com `eol=lf` mantido como fonte da verdade para tipos específicos.
- Layer 8 do pre-commit muda de BLOQUEIO para AVISO informativo (já que `autocrlf=true` resolve).
- Novo script `scripts/check_line_endings_config.py` que valida `core.autocrlf` de acordo com a plataforma (Windows=`true`, WSL=`false`/`input`), rodando no pre-push hook.
- Qualquer tentativa de auto-fix de CRLF no pre-commit é PROIBIDA — a correção raiz é configurar o Git corretamente, não tratar sintoma.


## 50. st.navigation dessincroniza apos render pesado (Revisao) - clique vira no-op

**Sintoma:** No CI, `test_all_pages_crawl` (smoke e2e) falhava em Capacidade: URL
revertia para /revisao. Nao reproduzivel com clique unico local (Capacidade como 2a
navegacao funcionava). O teste e2e REAL passava (clica Capacidade como 2a nav, fresh).

**Causa raiz:** Streamlit 1.59.0 `st.navigation` - apos o render de uma pagina pesada
(Revisao), o handler de click dos links da sidebar fica dessincronizado por ~3-4s. Os
primeiros cliques viram no-op (URL nao muda) MESMO com o <a> tendo href correto e
sendo clicavel (provado: elementFromPoint retorna o anchor certo, e el.click() JS tambem
nao navega). Reproduzido localmente: saindo de Revisao, os 3 primeiros cliques sao
ignorados, depois recupera. NAO e por contagem de navegacoes, NAO e auth.

**Correcao:** `tests/e2e/test_e2e_smoke_basic.py` usa `_click_nav_until_url()` que clica
o link real da sidebar e POLLA a URL (ate 8 tentativas x 2.5s) re-clicando, igual ao
`test_e2e_real.py` que usa `expect(page).to_have_url(timeout=10000)`. Mantem a sessao
SPA (sem reload) para preservar o login em `st.session_state`. Fallback via `page.goto`
NAO serve: reload completo destroi `st.session_state.authenticated` e volta para o login.


## 51. st.dataframe quebra (pyarrow ArrowInvalid) com coluna JSONB lista mista

**Sintoma:** No CI (Supabase REAL), a pagina "Scrapers & Logs" (e "Scraper Health > Raw Logs")
quebrava com `pyarrow.lib.ArrowInvalid: ('cannot mix list and non-list, non-null values',
'Conversion failed for column errors with type object')`. Localmente (Supabase fake/empty) nao reproduzia.

**Causa raiz:** `get_recent_scraper_logs()` faz `scraping_logs.select('*')` e a coluna
`errors` e JSONB — vem como LISTA em algumas linhas e NULO/escalar em outras.
`pd.DataFrame(logs)` cria uma coluna `object` mista, e `st.dataframe()` serializa via
pyarrow, que NAO aceita lista mista com escalares -> ArrowInvalid. So aparece no CI
(dados reais) e fica mascarado localmente.

**Correcao:** Em `dashboard/pages/scrapers.py` e `scraper_health.py`, normalizar a coluna
`errors` para STRING (lista -> ', '.join; dict -> json.dumps; None -> '') ANTES de passar
ao `st.dataframe`. So afeta as 2 paginas que exibem `scraping_logs` cru. Paginas que
usam `get_store_health()` (errors como int) nao tem o problema.

**Regra preventiva:** Nunca passar DataFrame com coluna object contendo listas/dicts mistos
a `st.dataframe`/`st.table`. Sempre stringificar colunas JSONB antes do display.


## 52. Lock files gerados no Windows causam drift no CI (colorama/tzdata)

- **Data + commit**: 2026-07-12 (07e6466)
- **Sintoma**: `dependency-audit.yml` job `lock-validation` falhava com `requirements.lock is out of sync with .in files` (e potencialmente os outros 3 lock files). O `git diff` mostrava `colorama==0.4.6` e `tzdata==2026.3` presentes nos locks commitados mas ausentes na regeneração do CI.
- **Causa raiz**: `pip-compile` no **Windows** resolve `colorama` (dependência condicional do `click`/`tqdm`/`typer`/`bandit`/`pytest` para Windows) e `tzdata` (necessário para `pandas` no Windows). No **CI (Ubuntu Linux)**, esses pacotes NÃO existem — o pip resolve dependências de plataforma nativamente. Lock files gerados no Windows sempre terão esses pacotes; lock files gerados no Linux nunca terão. Resultado: `git diff --exit-code` falha.
- **Correção**: Removido `colorama==0.4.6` e `tzdata==2026.3` dos 4 lock files (prod/dev/test/requirements.lock). `requirements.lock` = `cp requirements-test.lock` (como o CI faz). Para regenerar corretamente: **sempre usar WSL/Ubuntu** (Docker ou `custodoce-314`) com `PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu pip-compile --allow-unsafe`.
- **Teste de regressão**: O próprio CI (`dependency-audit.yml` → `lock-validation`) é o teste — se os locks divergirem, o job falha em <2min.

**Regra preventiva**: Lock files (`.lock`) devem ser gerados **SEMPRE em Linux** (WSL `custodoce-314` ou Docker `python:3.14-slim`) — NUNCA no Windows. Pacotes condicionais de plataforma (`colorama`, `tzdata`, `win32api`, etc.) entram apenas no OS que os precisa, causando drift silencioso entre Windows/CI-Linux.
