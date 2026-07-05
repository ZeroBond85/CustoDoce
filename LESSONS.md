# Lições Aprendidas

> Extraídas de AGENTS.md. Numeração original preservada.
> Regras de execução/ambiente → `REGRAS.md`.

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
