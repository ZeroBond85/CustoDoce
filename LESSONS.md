# Lições Aprendidas
> Última atualização: 2026-07-09

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

### 51. Materialized view `v_latest_prices` precisa de RLS anon para o dashboard ler na nuvem

**Causa raiz:** O dashboard lê `v_latest_prices` via cliente ANONIMO (`get_supabase` -> `SUPABASE_ANON_KEY`). A view era `MATERIALIZED VIEW` sem `ENABLE ROW LEVEL SECURITY` nem `CREATE POLICY anon_read`. Materialized views NAO herdam RLS da tabela-base. Na nuvem (RLS ativo) a view retornava VAZIA para o anon -> `visao_geral`/`precos`/`promocoes` quebravam no E2E real (erro REAL, nao do teste).

**Solucao:** Adicionar em `scripts/deploy_database.py::generate_consolidated()` (PHASE 15c) e em `supabase/consolidated_migration.sql`:
```sql
ALTER MATERIALIZED VIEW v_latest_prices ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read" ON v_latest_prices FOR SELECT USING (true);
```
Aplicar via `python scripts/deploy_database.py --execute` (RPC 443) + `REFRESH MATERIALIZED VIEW CONCURRENTLY v_latest_prices`.
Evidencia: cliente anon retorna 5 linhas apos o deploy (antes retornava 0).

**Regra permanente:**
- Toda materialized view lida pelo dashboard via anon key PRECISA de policy `anon_read` explicita.
- Nova migration SQL vai em `deploy_database.py::generate_consolidated()` (REGRAS.md #8) e no `consolidated_migration.sql`.
- Sempre validar leitura anon da view apos criar/alterar RLS.
