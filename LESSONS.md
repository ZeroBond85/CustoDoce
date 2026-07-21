# Lições Aprendidas
> Última atualização: 2026-07-21 17:40 UTC

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

### 8. `PIP_INDEX_URL` → `PIP_EXTRA_INDEX_URL`

Para torch CPU em CI: use `PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu`. `PIP_INDEX_URL` SUBSTITUI PyPI e quebra `ruff`/`mypy`.

### 9. `get_supabase()` deve ter fallback se `SUPABASE_ANON_KEY` faltar

```python
# ✅ CERTO:
key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
```

`get_supabase()` prefere `SUPABASE_ANON_KEY` mas aceita `SUPABASE_SERVICE_ROLE_KEY` como fallback.

### 10. `SUPABASE_ANON_KEY` deve ser passado explicitamente nos jobs CI

A secret existe no GitHub mas precisa ser mapeada no workflow. Sempre adicionar `SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_ANON_KEY }}`.

### 11. `exec_sql_query` RPC — sem trailing semicolons

SQL com `;` no final quebra a subquery. Remova qualquer `;` no final de queries enviadas via `client.rpc("exec_sql_query", {"sql": sql})`.

### 12. Streamlit Cloud E2E flakiness — use continue-on-error + warmup agressivo

E2E contra infra externa que hiberna = sempre continue-on-error + warmup agressivo (min 6 rounds, 3min total). Verificar Lição #18 (failure() com continue-on-error).

### 13. Auto-disable scrapers — SEMPRE investigar causa raiz antes

Antes de mexer em `is_active`, fazer dry-run do `_auto_disable_if_needed`. Logs devem mostrar CAUSA detalhada.

### 14. Self-healing OBRIGATORIO em todos os scrapers

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

### 15. Causa raiz > Mascarar

Investigar raiz ANTES de aplicar patches. Logar `error_class` (Timeout|SSLError|LayoutChanged|...). Causa raiz ≠ log.message.

### 16. `hashFiles()` no GHA só funciona com arquivos trackados pelo git

```yaml
# ✅ CERTO:
if: steps.file.outputs.filename != ''
```

### 17. `if: failure()` não dispara dentro de `continue-on-error: true` jobs

Use `if: always() && steps.meu_teste.outcome == 'failure'` e adicione `id:` ao step.

### 18. Script inline Python em heredoc no YAML — delimiter na coluna 0

Solução: extrair para arquivo `.py` separado.

### 19. Streamlit Cloud virou SPA (React) — HTTP warmup é inútil

Playwright (browser real) é obrigatório. CI (push/PR) usa localhost:8501. Schedule mensal testa cloud real.

### 20. `page.wait_for_timeout()` é frágil para cold start E2E — use polling

Sempre usar polling (45s) para elementos que dependem de renderização assíncrona.

### 21. `httpx>=0.28` pode resolver para 1.x — sempre pin upper bound

```txt
# ✅ CERTO:
httpx>=0.28,<1.0
```

### 22. "Pré-existente" não é desculpa — corrija ou prove que é bloqueado

"Pré-existente" exige prova. Se é 1-5 linhas e não quebra nada, corrija agora.

### 23. Migration SQL nova precisa ser incluída em `deploy_database.py`

Toda migration SQL nova DEVE ser adicionada ao `generate_consolidated()`.

### 24. Novo código = novos testes

Módulo novo = `test_<modulo>.py` no mesmo PR. Unitários puros primeiro (mock I/O), integração depois.

### 25. Push → Acompanha CI até PASS

Análise prévia → resiliência durante → completude no fim. `--no-verify` só em emergência real, com justificativa no commit.

### 26. Sidebar/navigation NÃO renderizava em headless por TypeError/AttributeError silencioso

Root cause: `get_longitudinal_winners()` sem argumento `days` + `normalized` bool em vez de dict. Fix: `days=90` + `isinstance` guard.

### 27. Normalized pode ser `true` (bool) no Supabase — NUNCA use `p.get("normalized") or {}`

Commit: `da3e9f6`. SEMPRE proteger com `isinstance(raw, dict)` antes de `.get("price_per_kg")`. 21 ocorrências em 7 arquivos.

### 28. Schema Sync Validation — pre-req obrigatório antes de push

3 camadas: Contract tests (`test_dashboard_query_shapes.py`) + Schema introspection (pre-push) + Mocks realistas (dump real).

### 29. Mocks devem refletir realidade — gerar de dump real, não hand-crafted

Fixtures de teste = dump real do Supabase. Se mock precisa de caso edge, adicionar explicitamente ao fixture real, não inventar.

### 30. Contract tests como primeira linha de defesa — não E2E

Novo query em `dashboard_queries.py` = novo teste em `test_dashboard_query_shapes.py` no MESMO PR. E2E é validação de UX, não de schema.

### 31. CI leve para iteração E2E — não queimar free tier no pipeline completo

Iteração de bug E2E = branch + `ci-e2e-only.yml` (~4 min). Full CI só no merge final.

### 32. AGENTS.md sanitization (Sprint 11) — schema, split, agents_tool.py

AGENTS.md cresceu para 974 linhas, misturando lições, regras infra, ambiente e projeto vivo. Split em 3 arquivos + schema YAML + ferramenta de gestão:

- `config/agents_schema.yaml` — schema que define o que pode entrar no AGENTS.md (headings, max_lines, blocked patterns)
- `scripts/agents_tool.py` — ponto único de entrada: `--check`, `--full`, `--add-rule`, `--add-lesson`, `--status`
- 3 gatilhos de validação: pre-commit (+1s se AGENTS.md staged) → pre-push (+1s, agents_tool --check) → CI docs-sync (+8s)

Regra permanente:
- AGENTS.md mantido em ~350 linhas máximo
- Lições novas vão para LESSONS.md (via `--add-lesson`)
- Regras novas de execução vão para REGRAS.md
- CI valida schema a cada push/merge

### 33. 30 bugs de schema mismatch na auditoria manual do dashboard

30 bugs de schema mismatch encontrados na auditoria manual de 19 páginas do dashboard contra information_schema real do Supabase. Todo dict key access em páginas Streamlit deve ser validado contra schema real (SELECT column_name FROM information_schema.columns WHERE table_name=...). Mocks de teste DEVEM refletir schema real — nunca hand-crafted com keys imaginarias.

### 34. Drift skills ↔ docs ↔ disco é recorrente — SST operacional

**Causa raiz:** `sync_docs.py` detectava drift numérico (test counts, pages) mas nunca inspecionava `.opencode/skills/`. Skills podiam ser adicionadas/removidas sem qualquer falha em CI. Três verdades conflitavam: disco, `APPROVED_SKILLS` (hardcoded), e docs.

**Solução aplicada:**
- SST = disco (`.opencode/skills/`) + `APPROVED_SKILLS` + `docs/skills.md` (auto-gerado)
- `sync_docs.py` agora varre skills: `_check_skills_sync()` detecta disco ≠ approved ≠ docs
- `_sync_skills_md()` regenera `docs/skills.md` a partir do disco + categorias
- pre-commit Layer 6: bloqueia se skills mudarem sem `docs/skills.md`
- CI docs-sync job: `sync_docs --check --strict --experimental` falha se drift

**Regra permanente:** Toda skill nova = SST em 3 lugares verificáveis. `sync_docs --check` é o portão. Não editar `docs/skills.md` manualmente.

### 35. Dependency drift recorrente — auditoria automatizada obrigatória

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

### 36. Sprint 13 — Saneamento de working tree com `scripts/sanitize.py`

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

### 37. CI status check antes de push — pipeline verde ou bloqueia

Antes de qualquer push para `master`, verificar se o CI está verde. O pre-push hook step [0/5] faz essa checagem automaticamente:
- CI verde → OK, prossegue
- CI vermelho → **AVISO OBRIGATÓRIO** (não bloqueia — paradoxo: pode ser o fix que vai tornar o CI verde)
- `gh` não autenticado → **AVISO** para configurar

Ordem: primeiro verificar CI, depois executar os demais steps locais.

Autenticação: `gh auth login` ou `GH_TOKEN` no `.env`. Responsabilidade do desenvolvedor de não pushar sobre CI vermelho a menos que seja a correção.

### 38. Monitoração é essencial — se não é monitorado, assuma que está quebrado

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

### 39. Monitoração de CI em shells com timeout (Polling vs Watch)
  
 **Causa raiz:** O comando `gh run watch` mantém uma conexão aberta e aguarda a conclusão do run. Em ambientes de shell com timeout estrito (ex: 120s), o comando é interrompido prematuramente, impedindo o acompanhamento do CI até o fim.
  
 **Solução:** Substituir o "Watch" por "Polling" (consultas repetidas e curtas).
  
 **Técnica de Polling:**
 `gh run view <run_id> --json conclusion --jq '.conclusion'`
  
 **Regra permanente:** Agentes devem implementar loops de polling com intervalos (ex: 30s) para monitorar a conclusão do CI, evitando a dependência de comandos de watch de longa duração.
 
### 40. Scheduled workflows não devem usar GH_PAT custom token no Checkout
**Causa raiz:** No run https://github.com/ZeroBond85/CustoDoce/actions/runs/28803088935 (scheduled, master), o Checkout falhou 3× com `fatal: could not read Username for 'https://github.com': terminal prompts disabled` porque `with: token: ${{ secrets.GH_PAT }}` força prompt interativo ausente em modo scheduled; e o `python -c "import httpx"` nos alertas de commit/e-mail também quebrou (provavelmente por ambiente restrito).
**Solução:** Remover `with: token:` do step "Checkout" em `.github/workflows/scrape.yml` (mantido o default); substituir `python -c "import httpx"` por `curl -X POST` direto nos passos "Alert on commit failure" e "Alert on email failure"; GH_PAT preservado apenas no step "Commit Latest Pushing latest prices" (git push).
**Validação:** Run https://github.com/ZeroBond85/CustoDoce/actions/runs/28803210736 (on_demand_scrape.yml, scheduled) rodou verde com checkout sem token. Novo teste unitário `tests/unit/test_scrape_workflow.py` garantindo que `.github/workflows/scrape.yml` NÃO contém `token: ${{ secrets.GH_PAT` no step de checkout.
**Data:** 2026-07-06

### 41. GH Actions Step Validation

Steps sem 'run:' ou 'uses:' geram 'failure' com 0 jobs. yaml.safe_load nao detecta. Validar com test_all_steps_have_run_or_uses() antes de push.

### 42. git_push.py timeout — Polling obrigatório para CI Watch em shells com timeout

**Causa raiz:** O script `scripts/git_push.py` usa `gh run watch --exit-status` (linha 136-141) que mantém conexão aberta até o CI completar. Em shells com timeout estrito (ex: 120s padrão), o comando é interrompido prematuramente, perdendo o status final do CI (success/failure) e impedindo o auto-retry.

**Solução:** Substituir `gh run watch` por polling assíncrono com `gh run view <run_id> --json conclusion` em loop (intervalo 30s) — igual à técnica da Lição #42. O timeout do subprocesso deve ser `CI_WATCH_TIMEOUT` (padrão 600s), não o timeout do shell.

**Regra permanente:** 
- `git_push.py` DEVE implementar polling, não `gh run watch`
- Todo agente que monitorar CI deve usar polling repetitivo até conclusão final
- Se shell timeout < tempo do CI, o watch falha e perde a conclusão

### 43. Serviços com dependências opcionais — retorne False, não levante exceção

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

### 44. Scripts referenciados em workflows devem ter test de existência

**Causa raiz:** `scripts/enrich_prices.py` estava referenciado em `.github/workflows/scrape-reusable.yml` mas o arquivo nunca existiu no repositório. A CI rodou 3 vezes (`enrich` job fail) até o script ser criado.

**Solução:** Criar `scripts/enrich_prices.py` + adicionar `test_enrich_prices_script_exists()` em `test_ci_infrastructure.py`.

**Regra permanente:** TODO script referenciado em qualquer workflow YAML deve ter um test de existência correspondente em `tests/unit/test_ci_infrastructure.py`.

### 45. `pip-audit --strict` NÃO significa "falha em vulnerabilidades"

**Causa raiz:** Workflow `ci.yml` usava `pip-audit --strict -s osv -r requirements.txt` no step "Audit dependencies". O flag `--strict` no pip-audit 2.x significa **"falha se a COLETA de dependências falhar"** (não "falha em vulns"). Em CI (ubuntu/Py3.14) a coleta de alguma dependência de `requirements.txt` falha → exit 1 mesmo com "No known vulnerabilities found". Combinado com `set -e` implícito do GitHub Actions, o script morria antes do check de severidade.

**Solução:** Remover `--strict` (pip-audit falha por padrão em vulns reais) + capturar exit code explicitamente (`set +e` / `set -e`) para não abortar o script. Bloquear só em HIGH/CRITICAL via grep de `Severity:`.

**Regra permanente:**
- Nunca usar `pip-audit --strict` para "falhar em vulnerabilidades" — esse é o comportamento DEFAULT
- `--strict` = falha em erro de COLETA de dependência (falso positivo em ambientes com extra-index-url, Py3.14, etc.)
- Em workflows, sempre capturar exit code de pip-audit explicitamente (`set +e` antes, `set -e` depois) para o check de severidade rodar

### 46. Falha de CI pré-existente = GAP de teste, tratar imediatamente

**Causa raiz:** O pre-push hook avisou "CI está vermelho" (master com F401 em `test_alert_service.py`/`test_telegram_service.py` + pip-audit bug). O agente tratou como "não são nossas mudanças, fora de escopo" e seguiu. Isso viola AGENTS.md regra #11 ("Falha no CI = Gap de Teste... 'Tentar de novo' é proibido").

**Solução:** Reproduzir a falha de CI localmente (`gh run view <id> --log-failed`), corrigir na branch feature (rebase onto origin/master + fix), e registrar LESSONS.md. No caso: F401 `import pytest` não usado (removido) + pip-audit `--strict` (removido).

**Regra permanente:**
- Se o pre-push avisa "CI vermelho", NÃO é desculpa para ignorar — investigar e corrigir
- Falha de CI pré-existente continua sendo GAP de teste se não for tratada antes do merge
- Sempre reproduzir localmente + corrigir + LESSONS.md (mesmo que o bug não venha das nossas mudanças)

### 47. E2E real/interactions: login exige usuario E senha; sidebar usa <a> (st.navigation)

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

### 48. Testes de conftest que carregam .env não isolam — monkeypatch `dotenv.load_dotenv` para no-op

- **Data + commit**: 2026-07-09 (sessão saneamento-fase-1 pré-tornar-público)
- **Sintoma**: `tests/unit/test_conftest_missing_creds.py::test_has_real_db_false_quando_env_vazio` (após reorganização do arquivo: `test_has_real_db_false_quando_env_minimo`) falhava intermitentemente em CI. `module._has_real_db() is False` falhava porque retornava `True`. Outros 4 cenários passavam.
- **Causa raiz**: `tests/conftest.py:23` chama `load_dotenv(Path(__file__).resolve().parent.parent / ".env")` **incondicionalmente no import do módulo**. Quando o teste carrega conftest em módulo isolado (`spec_from_file_location`) com `os.environ` limpo + `monkeypatch.delenv("SUPABASE_URL", raising=False)`, o `load_dotenv` é executado **DENTRO do `exec_module`** e **injeta o `.env` real do projeto** em `os.environ` ANTES do `delenv` aplicar (o `monkeypatch.delenv` foi feito antes do exec, mas o `load_dotenv` re-injeta durante o exec). Resultado: o módulo carregado tem `SUPABASE_URL` populada, `_has_real_db()` retorna True.
- **Correção**: Em `tests/unit/test_conftest_missing_creds.py` adicionei `monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)` **antes** do `spec.loader.exec_module(module)`. Assim o módulo carrega sem `load_dotenv` substituir nada em `os.environ`. 5/5 testes passam.
- **Teste de regressão**: Coberto pelos 5 cenários existentes `test_has_real_db_*` em `tests/unit/test_conftest_missing_creds.py` — sem o monkeypatch de `load_dotenv`, **nenhum** dos 5 passa de forma confiável quando existe `.env` no projeto (cenário local-dev).

**Regra permanente:**
- Ao testar módulos que chamam `load_dotenv(...)` no import, **sempre** monkeypatch `dotenv.load_dotenv` para no-op ANTES de `exec_module` em testes de isolamento.
- `monkeypatch.delenv` sozinho **não basta** se o módulo re-injeta valores durante import via `load_dotenv`.
- Alternativa: usar `load_dotenv(..., override=True)` no conftest para permitir que CI (env vars) sobreponha `.env` local — mas isso muda semântica do conftest em produção. Preferível patchar no teste.

### 49. sync_docs.py --sync so rodava v2 (CURRENT blocks) — README/REGRAS/API/timestamps ficavam desatualizados
- **Sintoma/causa/correcao**: `sync_docs.py` chamava so os updaters v2 (CURRENT blocks); os v1 (README/REGRAS/AGENTS/API/timestamps) nao rodavam no `--sync`, gerando drift no CI. Tambem: contagem de testes usava regex `tests? collected` mas pytest imprime `items collected`. Fix: `--sync` roda v1 depois v2; regex ajustado p/ `items`; tolerancia +-5 na contagem.

### 50. Auditoria profunda de testes (Fases 0-9) — 2026-07-11

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
### 51. .gitignore data/store_backups/ — 2026-07-11

**Sintoma:** 3 backups YAML idênticos (115KB) commitados em data/store_backups/ (commit 22fd346).

**Causa:** Script de backup (scripts/backup_stores_yaml.py) escreve em data/store_backups/ mas pasta não estava no .gitignore.

**Correção:** Adicionar `data/store_backups/` ao .gitignore (seção ML/model artifacts).

**Regra permanente:** Qualquer pasta que scripts escrevam automaticamente (backups, cache, dumps) → adicionar ao .gitignore ANTES do primeiro commit.

---
### 52. Guard rule3_db_password — 2026-07-11

**Sintoma:** Regra #3 AGENTS.md (NUNCA psycopg2/5432, SOMENTE RPC 443) não era enforceada automaticamente.

**Correção:** Criar `tests/unit/test_rule3_db_password_guard.py` (AST check) que falha se algum teste usar SUPABASE_DB_PASSWORD.

**Regra permanente:** Guard AST em pre-commit/CI para anti-patterns críticos (senhas, portas proibidas, imports perigosos). Rodar em `ci.yml` job `lint`.

---
### 53. Cleanup testes mortos — 2026-07-11

**Sintoma:** 5 arquivos testes mortos acumulados:
- test_sync_md_catchup.py + test_sync_md_catchup.py (script morto)
- test_brand_extractor.py (duplicado de test_services/test_brand.py)
- test_playwright_local.py (skip permanente)
- test_unit_extractor.py (10 testes p/ 18 LOC)
- deploy-staging.yml.disabled (workflow obsoleto)

**Correção:** Fase 13 — remover com `git rm` e atualizar .gitignore se necessário.

**Regra permanente:** Antes de adicionar teste novo, verificar se similar já existe. `git grep "test_" -- tests/` antes de criar.

### 54. AsyncMock.return_value padrão é AsyncMock, não MagicMock

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

### 55. Marcador `slow` para documentação, não filtro automático

**Decisão:** `test_alert_service.py` (1 teste ~32s) marcado como `@pytest.mark.slow`. O `addopts` global **não** inclui `-m 'not slow'` para evitar quebrar workflows CI que rodam testes lentos (diagnostics, real, integration). O marcador serve como documentação e filtro opcional. Para pular testes lentos localmente: `pytest -m 'not slow'`.

### 56. CRLF root fix: `core.autocrlf = true` no Windows — WSL não precisa

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

### 57. st.navigation dessincroniza apos render pesado (Revisao) - clique vira no-op

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

### 58. st.dataframe quebra (pyarrow ArrowInvalid) com coluna JSONB lista mista

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

### 59. Lock files gerados no Windows causam drift no CI (colorama/tzdata)

- **Data + commit**: 2026-07-12 (07e6466)
- **Sintoma**: `dependency-audit.yml` job `lock-validation` falhava com `requirements.lock is out of sync with .in files` (e potencialmente os outros 3 lock files). O `git diff` mostrava `colorama==0.4.6` e `tzdata==2026.3` presentes nos locks commitados mas ausentes na regeneração do CI.
- **Causa raiz**: `pip-compile` no **Windows** resolve `colorama` (dependência condicional do `click`/`tqdm`/`typer`/`bandit`/`pytest` para Windows) e `tzdata` (necessário para `pandas` no Windows). No **CI (Ubuntu Linux)**, esses pacotes NÃO existem — o pip resolve dependências de plataforma nativamente. Lock files gerados no Windows sempre terão esses pacotes; lock files gerados no Linux nunca terão. Resultado: `git diff --exit-code` falha.
- **Correção**: Removido `colorama==0.4.6` e `tzdata==2026.3` dos 4 lock files (prod/dev/test/requirements.lock). `requirements.lock` = `cp requirements-test.lock` (como o CI faz). Para regenerar corretamente: **sempre usar WSL/Ubuntu** (Docker ou `custodoce-314`) com `PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu pip-compile --allow-unsafe`.
- **Teste de regressão**: O próprio CI (`dependency-audit.yml` → `lock-validation`) é o teste — se os locks divergirem, o job falha em <2min.

**Regra preventiva**: Lock files (`.lock`) devem ser gerados **SEMPRE em Linux** (WSL `custodoce-314` ou Docker `python:3.14-slim`) — NUNCA no Windows. Pacotes condicionais de plataforma (`colorama`, `tzdata`, `win32api`, etc.) entram apenas no OS que os precisa, causing drift silencioso entre Windows/CI-Linux.

### 60. `load_stores()` dropava silenciosamente lojas sem `scrape_frequencies`

- **Data + commit**: 2026-07-13
- **Sintoma**: ~64/71 lojas ativas em YAML nunca apareciam no pipeline — `collect_*()` sempre retornava vazio para a maioria dos scrapers. O log não mostrava erro, apenas "0 stores".
- **Causa raiz**: `services/collector.py:63-65` — `load_stores()` fazia `.select("store_id").eq("enabled", True)` e usava interseção (`in enabled_ids`). Lojas **sem nenhuma linha** em `scrape_frequencies` eram excluídas silenciosamente. A maioria das lojas reativadas não tinha freq row.
- **Correção**: `services/collector.py:58-71` — agora carrega TODAS as linhas de scrape_frequencies (incluindo `enabled=False`). Lojas sem freq row passam pelo filtro; apenas lojas com `enabled=False` explícito são excluídas (kill-switch).
- **Teste de regressão**: `test_validate_mocks_against_manifest` (indireto — validar que o mapper cobre todas). Teste direto ainda não escrito.

### 61. Type-drift: FKs `INTEGER`/`UUID` para `stores(id)` quando `stores.id` é `TEXT`

- **Data + commit**: 2026-07-13
- **Sintoma**: Migrations `006_scrape_requests.sql` e `009_store_registry.sql` declaravam `store_id INTEGER REFERENCES stores(id)` e retorno `id UUID` em `find_similar_store()` — incompatíveis com `stores.id TEXT`.
- **Causa raiz**: `stores.id` foi migrado de `UUID`/`INTEGER` para `TEXT` (slug) em seed.sql/consolidated, mas migrations mais antigas nunca foram atualizadas. `deploy_database.py` já corrigia `scrape_frequencies` inline (linhas 65-82) mas carregava `006` e `009` verbatim.
- **Correção**:
  - `supabase/migrations/006_scrape_requests.sql:7`: `INTEGER` → `TEXT`
  - `supabase/009_store_registry.sql:72`: `id UUID` → `TEXT` (assinatura)
  - `supabase/009_store_registry.sql:92`: `v_store_id UUID` → `TEXT` (variável)
  - `supabase/migrations/008_store_registry.sql`: deletado (duplicata de 009)
- **Teste de regressão**: `validate_db_schema.py` deve ganhar um check de `REFERENCES stores(id)` com tipo `TEXT` — pendente.

### 62. Agregador Promotons roteado para scraper errado (`TiendeoScraper` em vez de `PlaywrightAggregatorScraper`)

- **Data + commit**: 2026-07-13 (f524ce6)
- **Sintoma**: Promotons sempre retornava 0 resultados, mesmo estando ativo. Nenhum erro — apenas silêncio.
- **Causa raiz**: Promotons estava classificado como `type: aggregator` + `scraper: aggregator_scraper` no YAML. Isso o roteava para `collect_aggregators_ssr()` → `_run_ssr_scraper()` → `TiendeoScraper(store)` (linhas 705-712). `TiendeoScraper` usa `data-testid="flyer_list_item"` — seletor do Tiendeo, que não existe no DOM do Promotons. O scraper correto já existia: `PlaywrightAggregatorScraper` com `PORTAL_CONFIG["promotons"]` em `playwright_scraper.py:58`.
- **Correção**: `config/stores.yaml:636,649`: mudou `type: aggregator` → `aggregator_js` e `scraper: aggregator_scraper` → `playwright_scraper`. Agora roteia para `collect_aggregators_js()` → `PlaywrightAggregatorScraper` que usa `get_portal_config("promotons")`.
- **Teste de regressão**: `validate_scrapers.py --validate` (rodar no WSL) deve mostrar items do Promotons.

### 63. F541 lint (f-string sem placeholder) escapou para o CI — validação local incompleta

- **Data + commit**: 2026-07-13 (49278da)
- **Sintoma**: CI job `lint` falhou com 7× `F541 f-string without any placeholders` em `scripts/validate_scrapers.py:41,53,54,55,148,193,197`.
- **Causa raiz**: `scripts/validate_scrapers.py` foi criado durante a sessão mas `ruff check .` não foi executado antes do commit. Validamos deploy, sync e FKs, mas pulamos o lint local.
- **Correção**: `scripts/validate_scrapers.py:41,53,54,55,148,193,197` — substituído `f"..."` por `"..."` (sem placeholder). Commit 49278da.
- **Teste de regressão**: `ruff check scripts/validate_scrapers.py` deve passar.

### 64. Lint F541 escapou porque pre-commit não incluía ruff — gap de processo

- **Data + commit**: 2026-07-13 (49278da)
- **Sintoma**: CI job `lint` falhou com F541 em `validate_scrapers.py` que não foi detectado localmente. CI job `docs-sync` também falhou — ambos escaparam porque validamos apenas deploy/sync/FKs, não `ruff check .` completo.
- **Causa raiz**: `.githooks/pre-commit` tinha 11 layers (secret, detect-secrets, doc sync, size, etc.) mas **não rodava ruff**. Nenhuma barreira local impedia commitar código com lint errado. A docs-sync também não tinha bloqueio no pre-commit para o caso geral (só para `.opencode/skills/` alterados).
- **Correção**: `.githooks/pre-commit` — adicionada **Layer 1.8: RUFF LINT** que roda `ruff check --quiet` em todos os `.py` staged e BLOQUEIA se houver erros. Agora o pre-commit tem 12 camadas de proteção.
- **Teste de regressão**: O próprio pre-commit é o teste — qualquer commit com `.py` que tenha lint error será bloqueado automaticamente.

### 65. Encartes vision-LLM (Max/Roldão/Giga): keys precisam estar no workflow de produção

- **Data + commit**: 2026-07-13
- **Sintoma**: Extração vision de encartes (Groq/Gemini) funcionava 100% local (`.env` carregado) mas falharia silenciosamente em produção — `scrape.yml`/`scrape-reusable.yml` só passavam secrets do Supabase, sem `GROQ_API_KEY`/`GOOGLE_API_KEY`.
- **Causa raiz**: Novos providers vision adicionados ao código (`parsers/vision_strategies.py`) sem wiring correspondente no `env:` do step de scraping nem na declaração `secrets:` do reusable workflow. Local ≠ produção (viola paridade, regra 10).
- **Correção**: (1) `scrape-reusable.yml` — `GROQ_API_KEY`/`GOOGLE_API_KEY` em `workflow_call.secrets` (optional) + `env:` do step `main.py --tier`. (2) `scrape.yml` e `on_demand_scrape.yml` — repassam ambos secrets. (3) `gh secret set` para os 2 valores validados.
- **Detalhes vision**: Groq (`llama-4-scout-17b`) é 3–8x mais rápido que Gemini (`gemini-2.5-flash-lite`) e igualmente preciso → **Groq primário, Gemini fallback** (chain Groq→Gemini→OpenRouter→HF). Gemini truncava JSON em `maxOutputTokens`; imagens grandes davam 413 → `_downscale_image` (PIL ≤1600px, JPEG ≤900KB). Giga: cards `img[class*=encartesSection__image]` já são páginas full-size — não precisa abrir modal.
- **Teste de regressão**: `tests/unit/test_services/test_flyer_ocr.py` (12) + `tests/unit/test_vision_strategies.py` (downscale/retry/gemini/fence). YAML dos workflows validado com `yaml.safe_load`.

### 66. Indentação de bloco malformada em stores.yaml passa despercebida até `yaml.safe_load`

- **Data + commit**: 2026-07-13
- **Sintoma**: 6 testes falharam com `yaml.parser.ParserError: expected <block end>` apontando para o bloco `Proplastik` (`config/stores.yaml:967`).
- **Causa raiz**: Sessão anterior deixou as 4 primeiras linhas do bloco Proplastik com 1 espaço a mais (3/5 espaços em vez de 2/4). YAML só quebra quando um item de sequência desalinha do resto — passou silenciosamente até um parse real.
- **Correção**: Re-indentado `- name`/`tier`/`type`/`is_active` para 2/4 espaços. Proplastik também desativado (`is_active: false`) — dava TIMEOUT de 532s e 0 cobertura, desperdiçando minutos do free-tier.
- **Teste de regressão**: `tests/unit/test_deploy_check.py::test_yaml_files_parse` e `test_stores_config.py` cobrem parse + schema de stores.yaml.

### 67. scrape_frequencies com linhas duplicadas quebra integração e load_stores

- **Data + commit**: 2026-07-15 (121d6c6)
- **Sintoma**: CI `#403` (f978595): `test_real_scrape_frequencies_join` → `AssertionError: Expected >=20 enabled frequencies, got 11`. Também `test_workflow_checks::test_all_workflows_have_concurrency` falhou porque `test_store_recovery.yml` não tinha `concurrency:` no nível raiz.
- **Causa raiz**: `scrape_frequencies` acumulou **6053 linhas para só 70 `store_id` distintos** (duplicatas de código legado). (a) O `.in_(store_ids)` com 708 IDs estoura o limite de 1000 linhas do PostgREST → amostra não filtrada/truncada → contagem errada no teste; (b) `services/collector.py:load_stores()` faz last-write-wins sobre as duplicatas, podendo excluir loja ativa se uma duplicata `enabled=false` vier por último.
- **Correção**: Deduplicado no Supabase (mantido 1 linha/`store_id`, `enabled=true` se houver) → 70 linhas limpas, 38 ativas+habilitadas. `test_store_recovery.yml` ganhou bloco `concurrency` no raiz. `record_failure` já roteia erros transitórios para `record_transient_failure` e não insere/duplica freq.
- **Teste de regressão**: `tests/integration/test_real_integration.py::test_real_scrape_frequencies_no_duplicates` (assere 0 duplicatas por `store_id`).

### 68. Config scraper-specific (browse_urls etc.) não sincronizava para o DB → lojas rodavam sem config em CI

- **Data + commit**: 2026-07-15
- **Sintoma**: No `test_store_recovery.yml`, Rede Krill "success" mas `collected: 0` após **hang de 600s** (browser inicia, nada mais logado); Chefon 0 produtos por 429. As 8 lojas reativadas falhavam em CI apesar de a config em `stores.yaml` estar correta.
- **Causa raiz**: `scripts/sync_all_store_fields.py` só sincronizava as colunas em `FIELDS`. Chaves específicas de scraper (`browse_urls`, `api_base`, `api_base_fallbacks`, `image_host_fallbacks`, `headers`, `verify_ssl`, `anti_bot`, `cloudflare`, `rate_limit`, `vision_timeout_seconds`, `store_slug`, ...) **não são colunas** da tabela `stores` e nunca eram persistidas. A coluna `config` (jsonb) existia vazia (`{}`) e `load_stores()` não a promovia ao topo. Resultado: em CI (config vem do DB, não do yaml) Krill sem `browse_urls` caía no `/busca?q=` quebrado (SPA não renderiza busca) → 23 ingredientes × termos, cada `goto` de 30s → estoura 600s → 0 produtos. Max sem fallbacks de DNS, Chefon sem `anti_bot`, Giga sem `vision_timeout_seconds`, Spani sem `store_slug` — todas capadas.
- **Correção**: (1) `sync_all_store_fields.py` roteia toda chave que não é coluna (`DB_COLUMNS`) para a coluna `config` (jsonb). (2) `collector._merge_store_config()` promove `config` ao topo do dict da loja (colunas reais têm precedência), aplicado em `load_stores()` e `test_single_store.py`. (3) Sincronizado no Supabase (69 lojas). Validado local: Krill coleta **80 produtos em 10.5s** (browse mode) vs. 0 antes.
- **Bugs correlatos corrigidos junto**: (a) `get_active_stores()` sem paginação → cap de 1000 linhas do PostgREST truncava lojas reais (725 ativas hoje, 675 fixtures `Cleanup Store`); agora pagina via `.range()`. (b) `test_single_store.py` resolvia via `load_stores` (excluía lojas pausadas por `scrape_frequencies.enabled`) → agora resolve por `get_store_by_name`; e retornava exit 0 com `collected==0` (mascarava timeout/429) → agora falha.
- **Teste de regressão**: `tests/unit/test_services/test_collector_config_merge.py` (merge de config), `tests/unit/test_config_db.py::test_get_active_stores_paginates_beyond_1000`, `::test_test_single_store_fails_on_zero_products`, `::test_test_single_store_resolves_paused_store`.

### 69. Spani não era Tiendeo — é e-commerce VipCommerce (mesma plataforma da Rede Krill)

- **Data + commit**: 2026-07-15
- **Sintoma**: Spani reativada mas sem fonte real: config antiga usava `type=aggregator`/`aggregator_scraper` (Tiendeo) com `url_pattern` S3 de placeholders literais que nunca resolveu. Raspar o site (Angular SPA) via Playwright era lento e frágil.
- **Causa raiz**: `spanionline.com.br` roda na plataforma **VipCommerce**, que expõe uma **API JSON pública** após login anônimo de loja. Raspar a API é ordens de magnitude mais rápido/estável que o SPA. Descoberta via captura de rede: `POST /org/{org}/auth/loja/login` (body com `domain`/`username`/`key`) → Bearer token; `GET .../departamentos/arvore` → 14 departamentos; `GET .../departamentos/{id}/produtos?page=N` → produtos paginados (`paginator.total_pages`). Spani: `org=67`, `filial=1`, `centro_distribuicao=15`.
- **Correção**: novo `scrapers/vipcommerce_api_scraper.py` (`VipCommerceApiScraper`) reutilizável: login → seleção de departamentos por palavra-chave de confeitaria (`chocolate`, `mercearia`, `cereais`, `laticinio`, `sobremesa`, ...) → paginação com teto `vip_max_pages_per_dept`. Registrado em `collector.API`/`collect_vipcommerce` (tier 2a, `type=vipcommerce_api`) e em `test_single_store.py`. Spani reconfigurada em `stores.yaml` com `vip_org_id/vip_filial_id/vip_cd_id/vip_login_key/vip_domain`. Validado E2E via `test_single_store`: **593 produtos, 93 matched & upserted** em ~90s.
- **Nota de eficiência**: browse por departamento traz muito produto irrelevante (593 → 93 matched); endpoint de busca targeted do VipCommerce (`/produtos/busca`) retorna 500 com params testados — não descoberto. `vip_max_pages_per_dept=6` equilibra cobertura (14/23 ingredientes; os ausentes não existem no catálogo Spani) vs. carga de matching/upsert. Krill (mesma plataforma) pode migrar para este scraper no futuro.
- **Teste de regressão**: `tests/unit/test_vipcommerce_api_scraper.py` (9 testes: login, seleção por keyword, parse de preço/oferta/unidade, paginação com teto, fluxos run success/fail).

### 70. Spawn de subprocesso no Windows degrada ~50x scrapers HTTP → Krill/Chefon travavam em CI

- **Data + commit**: 2026-07-15
- **Sintoma**: Krill (VipCommerce search) e Chefon (WebsiteScraper) coletavam 2 produtos em 130-160s via `_run_scraper_isolated` (spawn) quando o run direto (mesmo host) fazia 661/120 produtos em 66s/1.8s. O `store_timeout` (280s) matava o subprocesso → `collected: 0`.
- **Causa raiz**: no Windows, `multiprocessing` com `get_context("spawn")` sofre overhead enorme para requisições HTTP (provavelmente resolução/reuse de socket + cold start do interpretador filho). Scrapers **puramente HTTP** (sem browser) não precisam de isolamento de processo — não há Chrome que possa pendurar o pipeline. Scrapers com Playwright continuam isolados.
- **Correção**: (1) `BaseWebScraper.safe_in_parent` (default False); `VipCommerceApiScraper` e `WebsiteScraper` setam `safe_in_parent=True`. (2) `_scrape_store()` roda esses scrapers **no processo pai** (`scraper.run(...)`) quando `safe_in_parent`, com try/except + `record_failure`. Resultado: Krill 492 produtos em 67s, Chefon 120 produtos em 1.8s (sem isolamento).
- **Bugs correlatos da mesma investigação**: (a) Rede Krill migrada para `vipcommerce_api_scraper` `mode=search` (endpoint `/buscas/produtos/termo/{termo}`, org=216/filial=1/cd=20) + filtro `vip_search_ingredients` (16 que a loja carrega) p/ caber no orçamento; `_run_search` deduplica termos e o path de busca fica um nível acima de `/classificacoes_mercadologicas`. (b) Chefon: `browse_url_timeout: 35` por URL no `fetch_browse` (ThreadPoolExecutor com `result(timeout=)`) evita que UMA url Cloudflare travada segure o loop `browse_parallel` inteiro. (c) Max: `_normalize_image` trocava o host que responde 200 (`institucional.supermuffato.com.br`) por fallback que 404a (`maxatacadista.com.br`) → OCR do flyer baixava 0 bytes. Corrigido: `_normalize_image` só conserta `//` → `https:`, NÃO troca host; removido `image_host_fallbacks` do YAML.
- **Conclusão sobre Max**: após o fix, o flyer do Max roda e extrai produtos via vision-LLM, mas casa ~2/56 com os 23 ingredientes monitorados (é um flyer de supermercado geral — sem confeitaria). Isso é **correto**, não bug. Para o harness distinguir "viável" de "quebrado", `_scrape_store` agora popula `collector.LAST_RUN_STATS[store]={extracted, matched}` (raw extraído vs. casado). `test_single_store.py` lê esse dict — **sem re-raspar** (double-scrape gastaria vision-API e retornaria o mesmo `collected`, pois o collector devolve produtos JÁ casados, não o bruto): `extracted>0 & matched==0` = aprovado (flyer sem confeitaria), `extracted==0` = falha real.
- **Teste de regressão**: `tests/unit/test_scrapers.py::test_preserves_working_host`, `::test_keeps_existing_https_url`; `tests/unit/test_vipcommerce_api_scraper.py` (search mode); `tests/unit/test_services/test_collector_last_run_stats.py` (3 testes: record extracted/matched, extracted>0&matched=0 não é falha, extracted=0 é falha).

### 71. scrape_frequencies acumulou 424 linhas duplicadas → CI integration vermelho

- **Data + commit**: 2026-07-15. **Sintoma**: `test_real_scrape_frequencies_no_duplicates` falhou em CI: 424 duplicadas por `store_id` (494 vs 70 lojas). Era pré-existente (não do commit de recuperação).
- **Causa raiz**: `upsert_scrape_frequency()` chamava `client.table("scrape_frequencies").upsert(data)` **sem `on_conflict`**. Como a PK é `id UUID DEFAULT gen_random_uuid()`, cada upsert gerava uma NOVA linha em vez de atualizar — acumulando ~7 linhas/loja ao longo do tempo. Não havia unique index em `store_id` para impedir. `load_stores()` faz last-write-wins e o limite de 1000 linhas do PostgREST também era ameaçado.
- **Correção**: (1) Deduplicado o DB real via REST `delete().in_("id", ...)` (manter o `updated_at` mais recente por `store_id`): 494→70 linhas, 0 duplicatas. (2) `upsert_scrape_frequency` agora passa `on_conflict="store_id"`. (3) Nova migration `supabase/010_scrape_frequencies_unique.sql` + registrada em `generate_consolidated()` (PHASE 25): `CREATE UNIQUE INDEX uq_scrape_frequencies_store_id`. (4) Teste de regressão `tests/unit/test_services/test_config.py::test_upsert_scrape_frequency_uses_on_conflict_store_id` (mock captura `on_conflict`).
- **Nota**: `exec_sql_query` (443) só aceita SELECT. Regressão: `test_config.py::test_upsert_scrape_frequency_uses_on_conflict_store_id`; `test_real_integration.py::test_real_scrape_frequencies_no_duplicates` (verde).

### 72. Vision fallback falhava em 429: ~60s/imagem, estourava timeout do Max

- **Data + commit**: 2026-07-15. **Sintoma**: `test_store_recovery` do Max: `TIMEOUT 300s`, 0 produtos, 86x `[groq_vision] Rate limited`. Groq 429 em TODAS as imagens (10 encartes) obedecia `Retry-After: 30s` ×2 = ~60s/imagem; Gemini (fallback) deu 503/JSON invalido → nenhuma imagem extraída. Spani/Krill OK; Chefon falhou só por nome errado no arg.
- **Causa raiz**: (1) `get_vision_chain()` instanciava estratégias NOVAS a cada imagem → o circuit breaker resetava por imagem e NUNCA abria → Groq re-tentado 429 em todas as imagens. (2) Em 429, o codigo obedecia ao `Retry-After` (30s) em vez de ceder ao proximo provider. (3) Modelos fracos (`llama-4-scout-17b`, `llava-1.5-7b`) mal extraem JSON de flyer.
- **Correção**: (1) Cadeia em cache module-level (`_get_cached_chain()`) — breaker persiste entre imagens. (2) `VISION_FAIL_FAST_ON_429` (default on): em 429 com fallback, abre o breaker e retorna None sem esperar `Retry-After` → cadeia pula p/ Gemini/OpenRouter/HF. (3) `_has_fallback` por posição. (4) Modelos melhores: Gemini `gemini-2.5-flash` (era flash-lite), OpenRouter `llama-4-scout-17b:free` (era gemma-4-31b), HF `llava-1.5-13b-hf` (era 7b). (5) Krill: `_fetch_search_products` usa `quote_plus` (`20%` causava 400).
- **Teste de regressão**: `test_vision_strategies.py` (`test_cached_chain_returns_same_instances`, `test_cached_chain_breaker_persists_across_images`, `test_groq_429_opens_breaker_so_next_provider_is_tried`, `test_chain_marks_has_fallback_except_last`); `test_vipcommerce_api_scraper.py::test_fetch_search_products_url_encodes_percent`.

### 73. Store Recovery: usar o `name` exato da loja no arg da matriz

- **Data + commit**: 2026-07-15
- **Sintoma/causa**: recovery com `stores="...,Chefon Atacadista,..."` falhou (`loja não encontrada`); o arg usa o `name` exato da coluna `stores.name` e a loja no DB chama-se `Chefon`.
- **Correção**: passar sempre o `name` de `get_store_by_name`. Falha de entrada, não de scraper.

### 74. Zerar scrape_frequencies para forçar scrape full quebra a integração

- **Data + commit**: 2026-07-16
- **Sintoma/causa**: para rodar um scrape full "do zero" a frequência foi zerada no DB (`scrape_frequencies` 70→0). CI `integration` ficou vermelho: `test_d2_4_scrape_frequencies_enabled` e `test_real_scrape_frequencies_join` exigem `>=20 enabled`. Estado do DB, não código.
- **Correção**: NUNCA mutar dados para forçar coleta. Usar `--force` → `CUSTODOCE_FORCE_SCRAPE=1` (`main.py:225`), que faz `_should_skip_store` (`collector.py:351`) ignorar a freshness check sem tocar no DB. `scrape.yml` agora expõe input `force` (boolean) propagado ao reusable. DB repopulado via `scripts/sync_all_store_fields.py` (56 freqs, `on_conflict="store_id"`).
- **Teste**: `test_scrape_dispatch_exposes_force_input` (workflow expõe/propaga `force`) + `test_should_skip_store_bypassed_by_force_env` (force env não toca no DB).

### 75. Python 3.14 strict scoping: import local de `suppress` quebra `_collect_prices`

- **Data + commit**: 2026-07-16
- **Sintoma/causa**: Scrape (Tier 1/2a/3) falhou com `cannot access local variable 'suppress' where it is not associated with a value` em `collect_extra_flyers`, `collect_tier2_vtex`, `collect_carrefour`, etc. Causa: `from contextlib import suppress` DENTRO do `if safe_in_parent:` (collector.py:566) marca `suppress` como **local para toda a função**; nos branches do `except`/`finally` que usam `with suppress(...)` fora do `if`, o Python 3.14 levanta o erro (binding local não atribuído). Só falhava no caminho de erro (subprocesso/isolated), não no happy path — por isso os testes antigos não pegaram.
- **Correção**: removido o import local (já existe `from contextlib import suppress` no topo, linha 10). Sempre usar o import de módulo, nunca local dentro de branch que cria escopo.
- **Teste**: `test_suppress_local_scope_bug_in_parent_process` (exercita `safe_in_parent=False` + except → garante que `suppress` resolve).

### 76. Fallback de upsert_price usava `insert` → 23505 em force scrape

- **Data + commit**: 2026-07-16
- **Sintoma/causa**: Tier 3 (force scrape) reportou `duplicate key violates unique constraint "prices_ingredient_id_store_id_collected_at_key"` (23505). Quando o RPC `upsert_price_rpc` falha com `Resource temporarily unavailable` ([Errno 11], pressão do Supabase em scrape paralelo), o fallback fazia `table.insert()` sem `ON CONFLICT` → duplicata no mesmo `collected_at` do dia.
- **Correção**: fallback agora usa `table.upsert(data, on_conflict="ingredient_id,store_id,collected_at")` (espelha a constraint da RPC). Elimina 23505 mesmo sob pressão.
- **Teste**: `test_upsert_price_fallback` atualizado para validar `.upsert()` no caminho de fallback.

### 77. `await coroutine().lower()` quebra Promotons (Tier 3)

- **Data + commit**: 2026-07-16
- **Sintoma/causa**: Tier 3 (Scrape force) falhou com `[Promotons] Error scraping ...: 'coroutine' object has no attribute 'lower'`. Em `playwright_scraper.py:153` o código era `html_lower = await self._get_page_html(page).lower()` — o `await` aplicava-se ao resultado de `.lower()`, não à coroutine `self._get_page_html(page)` (que retorna coroutine porque é `async def`). Sem o `await` correto, `.lower()` era chamado no coroutine → AttributeError.
- **Correção**: `html_lower = (await self._get_page_html(page)).lower()` (parênteses em volta do await). `Tiendeo 403 Forbidden` e `Resource temporarily unavailable` (Supabase sob pressão) continuam como warnings transitórios — não são bugs.
- **Teste**: `TestPlaywrightCoroutineLowerBug::test_wait_for_real_content_awaits_html_before_lower` valida que `_get_page_html` resolve a str (não coroutine).

### 78. Scrape job não deve falhar por 403 de agregador (Tiendeo)

- **Data + commit**: 2026-07-16
- **Sintoma/causa**: Tier 3 falhava mesmo após corrigir os bugs de código, porque o grep do `scrape-reusable.yml` considerava `Client error '403 Forbidden'` (Tiendeo bloqueando o scraper) como erro fatal de job. O scraper já trata esse fetch error como `warning` e pula a loja (self-healing) — não é erro de código.
- **Correção**: removido `Client error|HTTP [45][0-9][0-9]` do padrão do grep. O job agora falha APENAS em erros de nível `[error]`/`falha no scraper` (bugs reais). 403 de agregador é warning esperado.
- **Teste**: `test_scrape_reusable_does_not_fail_on_client_error` valida que o grep do scrape-reusable não inclui `Client error`.

### 79. Pre-commit quebra se `python3` no PATH estiver corrompido

- **Sintoma/causa/correção**: commits sumiam (exit 1 sem msg) porque o hook resolvia `python3.exe` corrompido e `set -euo pipefail` abortava em `agents_tool.py --check`. Fix: `.githooks/pre-commit` usa `_detect_python()` que valida o interpreter (`import sys`) e prefere `.venv314/Scripts/python.exe`.
### 80. Push no Windows quebra (gh FileNotFound + sync_docs suja tree); RAIZ = WSL
- **Sintoma/causa**: `git_push.py` quebrava no pre-push com `FileNotFoundError: gh` (Python sem PATH do Git Bash). O pre-push também roda `sync_docs --sync`, re-gera `docs/api/*.md`+`docs/skills.md` e suja a tree → Git barra o push. E commits com `[skip ci]` faziam o GitHub pular o `ci.yml` inteiro (falso verde).
- **Correção (RAIZ)**: `git_push.py` injeta `_ensure_bin_path()` (Git Bash + GitHub CLI + dir do Python) antes de qualquer subprocesso; `_run()` retorna exit 127 em `FileNotFoundError`. Push completo é **obrigatório em WSL**; Windows `--no-verify` é emergência + `gh workflow run 'CI - Testes e Qualidade' --ref master` p/ disparar CI manualmente. **NUNCA `[skip ci]`** em código. Ver `REGRAS.md` §Pre-push.
### 82. Scrape full expos bugs reais (guard PEGOU): api_flyer perdia produtos + OpenRouter 404 loop
- **Sintoma/causa/correcao**: scrape `force=true` (run 29582782313) falhou Tier1 — Roldao extraiu 120 mas `collection_done total=1`; OpenRouter `404` repetido (guard PEGOU). RAIZ (1): `collect_tier1_api_flyers` roteava produtos vision (sem `image_url`) pelo pipeline flyer-IMAGE que descarta -> 0; fix: rotear por `_collect_prices`. RAIZ (2): modelo `mixtral-8x7b-instruct` descontinuado -> 404 por produto; fix: default `openrouter/free` + abrir breaker em 4xx. Testes: `test_collector_helpers`, `test_llm_strategies`, `test_vision_strategies`.

### 83. Chefon HTTP 429 (Cloudflare) — RAIZ via Shopify Storefront JSON API
- **Sintoma/causa/correcao**: Tier3 (run 29586242082) falhou `[error] Chefon HTTP 429`; `chefon.com.br` e Shopify atras de Cloudflare — HTML `/collections/*` retorna 429 mesmo c/ Retry-After (servidor pedia 60s, `max_delay=10` cortava). RAIZ (1) `_retry_with_backoff` cortava Retry-After; RAIZ (2) rota errada (HTML protegido). Shopify expoe Storefront API `/collections/<col>/products.json?limit=&page=` sem challenge (testada: 250/req, 7.031 SKUs em `/all`); `curl_cffi` NAO e necessario (httpx padrao funciona). Fix: (a) `_retry_with_backoff` respeita Retry-After integral (teto 300s); (b) `website_scraper.py` modo `shopify_json` (`_run_shopify_json`+`_fetch_shopify_page`+`_parse_shopify_product`); (c) `stores.yaml` Chefon `shopify_json:true`. Teste: `tests/unit/test_website_scraper.py` (4).

### 84. Security audit: scrape_requests sem RLS (F-01)
- **Sintoma/causa**: `scrape_requests` (criada em `migrations/006`) não tinha `ENABLE ROW LEVEL SECURITY` — qualquer `anon` (chave pública) podia ler/escrever/apagar. **Correção**: `supabase/011_scrape_requests_rls.sql` (PHASE 26 em `deploy_database.generate_consolidated`) habilita RLS + policies anon_insert/anon_read + service_role_all. **Teste**: `tests/unit/test_security_lints.py::test_scrape_requests_rls_migration_exists`, `::test_consolidated_includes_rls_migration`.

### 85. Security audit: shell injection em workflow (F-02)
- **Sintoma/causa**: `test_store_recovery.yml` interpolava `${{ github.event.inputs.stores }}` direto em `run:` (RCE no runner). **Correção**: passar via `env: STORES_INPUT` + referenciar `"$STORES_INPUT"`. **Teste**: `::test_test_store_recovery_no_direct_input_interpolation`.

### 86. Security audit: exec_sql inseguro no consolidated (F-04)
- **Sintoma/causa**: `consolidated_migration.sql` PHASE 17 definia `exec_sql`/`exec_sql_query` como SECURITY DEFINER sem `SET search_path`/REVOKE (duplicata da PHASE 23 segura). **Correção**: remover as definições inseguras da PHASE 17 (só comentário + cleanup). **Teste**: `::test_no_insecure_exec_sql_definition`.

### 87. Security audit: SSRF em flyer download (A-03)
- **Sintoma/causa**: `collector.py`/`flyer_ocr.py` faziam `httpx.get(image_url)` de URLs da tabela `flyers` sem allowlist + `follow_redirects=True`; `discover_urls.py` usava `verify=False` (MITM). **Correção**: `services/url_guard.py` (`is_safe_url`/`guard_url`) bloqueia IPs privados/loopback/metadata e domínios fora da allowlist; aplicado em `collector.py` e `flyer_ocr.py`; `discover_urls.py` sem `verify=False`. **Teste**: `::test_verify_false_removed_from_discover_urls`.

### 88. Security audit: CI gates mascarados (F-08) + rate limiter global (ST-06)
- **Sintoma/causa**: `ci.yml` tinha `continue-on-error: true` em `db_security_lint`/`detect-secrets` (viola regra #11); `login_page.py` usava chave fixa `"login"` no rate limiter (não throttleia atacante individual). **Correção**: (a) teste de regressão offline `tests/unit/test_security_lints.py` substitui o masking; removido `continue-on-error`. (b) `_client_key()` deriva IP de `X-Forwarded-For`/`X-Real-IP`/`st.context.remote_ip` com fallback `"login"`.

### 89. Security audit: service-role client exposto + AUTH_SECRET_KEY aleatório (S-04/S-07)
- **Sintoma/causa**: `get_service_client()` (bypass RLS total) era chamado de páginas de dashboard sem checagem de sessão; `auth.load_config()` gerava chave aleatória por processo se `AUTH_SECRET_KEY` vazio (footgun se JWT for usado). **Correção**: `require_service_client()` exige `st.session_state.authenticated`; `lojas_pendentes.py`/`lojas.py` migraram para ele; `load_config()` faz `raise` se vazio em produção (`APP_ENV=production`/`STREAMLIT_SERVER`).

