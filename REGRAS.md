# REGRAS.md — Ambiente, Hooks, Comandos
> Última atualização: 2026-07-08 21:16 UTC

> Ambiente de execução, hooks de git, comandos de rotina e configurações obrigatórias.
> Extraído de AGENTS.md original (seções "Ambiente", "Pre-commit/pre-push hooks", "OpenCode Skills Strategy").

## Ambiente: Escolha do Executor

| Tarefa | Executor | Motivo | Tooling |
|--------|----------|--------|----------|
| ruff, mypy, pytest (unit/schema) | **Windows** | Latência zero, sem overhead de WSL | `.venv314` |
| Dashboard (Streamlit) | **Windows** | Renderização e rede local nativa | `.venv314` |
| Scripts de deploy, DB, SQL | **Windows** | Python direto via RPC/HTTPS | `.venv314` |
| Shell scripts (.sh), Git complexo | **WSL (Debian)** | PowerShell quebra escapes/heredocs | Bash |
| Simular CI Linux, Scrapers Reais | **WSL (Debian)** | Idêntico ao GitHub Actions (Ubuntu) | `custodoce-314` (Conda) |
| Playwright, OCR (Tesseract) | **WSL (Debian)** | Browser automation e dependências SO | `custodoce-314` (Conda) |
| Testes E2E / Visual | **WSL (Debian)** | Estabilidade do Chromium Headless | `custodoce-314` (Conda) |

### ⚠️ Lei do Ambiente (Anti-Fricção)
1. **Proibido "Misturar" Shells**: Não execute `wsl bash -c '...'` para tarefas que podem rodar em Python no Windows. Use WSL apenas para dependências de SO.
2. **Isolamento de Paths**:
   - Windows $\rightarrow$ `C:\Zerobond\Code\CustoDoce`
   - WSL $\rightarrow$ `/mnt/c/Zerobond/Code/CustoDoce`
   - Nunca passe caminhos de Windows para o Bash sem converter para o formato `/mnt/c/`.
3. **Default Python**:
   - Windows: `.venv314` (PowerShell)
   - WSL: `custodoce-314` (Conda/Bash)
4. **Paridade de Versões (Obrigatório)**:
   - **Python local (Windows/WSL) DEVE ser igual ao CI (GitHub Actions)**.
   - Versão alvo definida em `pyproject.toml` `[tool.ruff] target-version` e workflows `PYTHON_VERSION`.
   - Antes de qualquer PR: `python --version` local == `PYTHON_VERSION` no CI.
   - Qualquer discrepância bloqueia merge — CI valida no alvo real.


## Windows (PowerShell) — Padrão para Python

```powershell
python --version    # deve ser 3.14+
python -m ruff check .
python -m mypy .
python -m pytest tests/unit tests/schema -q
```

## WSL (Debian) — Para Git/Shell/CI

```bash
# Sempre usar bash absoluto
bash /mnt/c/.../scripts/rewrite.sh
```

## Configurações Obrigatórias (Windows)

```powershell
git config core.hooksPath .githooks   # ativa hooks
git config core.autocrlf false         # LF = LF (nao converte CRLF)
git config core.fileMode false         # permissoes nao travam em Windows
```

## Pre-commit Hook (`.githooks/pre-commit`)

4 layers existentes:
1. **SECRET GUARD**: BLOQUEIA se `sk-*`, `gsk_*`, `sk-or-*` etc. forem staged (irreversível)
2. **DOC SYNC**: AVISA se código mudou sem changelog (usuário confirma com ENTER)
3. **SIZE GUARD**: BLOQUEIA se arquivo >100MB staged (GitHub rejeita)
4. **DOC WATCHDOG**: AVISO leve sobre tests/README

**Layer 5 (novo)**: Se AGENTS.md estiver staged, roda `python scripts/agents_tool.py --check`. Se falhar, bloqueia o commit.

## Pre-push Hook (`.githooks/pre-push`)

Checks (rodam em paralelo via ThreadPoolExecutor, exceto os sequenciais 1 e 2):
1. **Working tree limpo** (bloqueante) — `git status --porcelain`
2. **CI CHECK** (warn-only, timeout 15s): `gh run list --branch master` — pipeline vermelho = aviso (não bloqueia, pois o push pode ser a correção). Se `gh` não autenticado → avisa.
3. **Checks paralelos (bloqueantes)** — executados simultaneamente:
   - `audit_secrets --strict --since N` (N = commits desde `origin/master`; escaneia só o que será pushado)
   - `agents_tool --check`
   - `sync_docs.py --check --strict` (com **auto-fix**: drift → roda `--sync` → revalida; se falhar, bloqueia o push)
   - `ci_local.py --no-unit` (ruff + bandit + pip-audit + mypy + config validation; pip-audit com `--timeout 30`)
   - `validate_query_columns.py`
   - `audit_df_columns.py`
   - `generate_schema_manifest.py` + `pytest tests/unit/test_validate_mocks_against_manifest.py`
   - `check_environment_parity.py`

**Nota**: `sync_docs` roda **apenas** no pre-push (versão rigorosa `--check --strict` + auto-fix). O `ci_local.py` **não** roda mais docs-sync (evita duplicação de "2 docs sync"). Para checar manualmente: `python scripts/sync_docs.py --check --strict`.

**Otimização (Fase 1)**: checks independentes rodam em paralelo; wall-time ≈ max(ci_local, demais) em vez de soma. `audit_secrets` escopado a commits outgoing. Rede (`gh`, `pip-audit`) tem timeout.

### Resolução Automática de Python

O hook `pre-push` resolve o Python na seguinte ordem:

1. **Env var `CUSTODOCE_PYTHON`** — override explícito (ex: `export CUSTODOCE_PYTHON=~/custodoce-314/bin/python`).
2. **`~/custodoce-314/bin/python`** — venv WSL/Linux nativo (fora do repo).
3. **`.venv314/Scripts/python.exe`** — venv Windows nativo (dentro do repo).
4. **`.venv314/bin/python`** — venv Linux/WSL nativo (dentro do repo).
5. **`sys.executable`** — fallback (com AVISO se nenhum venv existe).

```python
# .githooks/pre-push
def _resolve_python() -> str:
    explicit = os.environ.get("CUSTODOCE_PYTHON")
    if explicit and Path(explicit).exists() and os.access(explicit, os.X_OK):
        return explicit
    home_venvs = [Path.home() / "custodoce-314" / "bin" / "python"]
    candidates = home_venvs + [
        REPO_ROOT / ".venv314" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv314" / "bin" / "python",
    ]
    for c in candidates:
        if c.exists() and os.access(c, os.X_OK):
            return str(c)
    return sys.executable  # fallback (AVISO)
```

**Por quê?** `sys.executable` no hook resolves o Python que invocou o git → pode ser Python 3.11 global se você rodar git fora do venv. O `_resolve_python()` força o uso do venv apropriado à plataforma → **paridade total** com CI/Cloud.

**Output do hook** mostra qual Python foi resolvido na 1ª linha:
```
  [python] usando venv: C:\Zerobond\Code\CustoDoce\.venv314\Scripts\python.exe
=== pre-push: validando...
```
ou
```
  [python] usando venv: /home/ericsf/custodoce-314/bin/python
=== pre-push: validando...
```

**Cross-platform**: mesmo hook funciona em Windows PowerShell, WSL bash, e macOS zsh. Cada plataforma tem seu venv canônico:
- **Windows**: `.venv314/Scripts/python.exe` (Python 3.14.6)
- **WSL**: `~/custodoce-314/bin/python` (Python 3.14.6 via uv)
- **macOS**: `~/custodoce-314/bin/python` (similar)

Fallback `sys.executable` só ocorre se nenhum venv existir — nesse caso o hook emite AVISO. **Recomendado**: criar `.venv314/Scripts/python.exe` (Windows) ou `~/custodoce-314/bin/python` (Linux/WSL) antes do push. CI: 9 workflows Python 3.14 (single source of truth).

Opt-in Unit Tests: `set CI_LOCAL_UNIT=1` (cmd) ou `$env:CI_LOCAL_UNIT="1"` (ps).

Emergência: `git push --no-verify` (não recomendado).

## Regra Obrigatória: Secrets SEMPRE em .env, nunca em comandos

**NUNCA** passar tokens, senhas ou chaves de API diretamente em comandos, args de CLI, URLs ou variáveis inline no terminal.

### ❌ Proibido
```powershell
# NUNCA faça isso:
set GH_TOKEN=ghp_xxx... && gh pr create
curl -H "Authorization: token ghp_xxx..." https://api.github.com/...
```

### ✅ Correto
```powershell
# .env (gitignored) contém a chave:
GH_PAT=ghp_xxx...

# Uso via env var do .env:
$env:GH_TOKEN = (Select-String -Path .env -Pattern "^GH_PAT=(.*)").Matches.Groups[1].Value
gh pr create

# Ou via script helper:
python scripts/gh_helper.py create-pr --title "..."
```

### Por quê?
1. **Shell history** — comandos ficam no `$env:USERPROFILE\AppData\Roaming\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt`
2. **Process listing** — `Get-Process` pode expor args de outros processos
3. **Logs de CI** — qualquer echo/vazamento acidental expõe o token publicamente
4. **Tool calls** — o assistente (OpenCode/AI) exibe o comando completo, incluindo o secret

### Exceção zero
- Se um secret aparecer em qualquer comando, pare e mova para `.env` imediatamente
- Se o secret já vazou (logs, histórico, PR), **revoque e rotacione** -- não confie que "ninguém viu"

## Scripts de Segurança

- `scripts/audit_secrets.py --strict` — varre histórico por chaves
- `scripts/install_hooks.sh` — instala/re-instala hooks (shell-based, via WSL)

## OpenCode Skills

Skills: ver [docs/skills.md](docs/skills.md) (gerado por `python scripts/sync_docs.py --sync`).

SST (Single Source of Truth) = disco (`.opencode/skills/`) + `APPROVED_SKILLS` em `scripts/skills_maintenance.py`.

**Não editar manualmente.** Qualquer alteração em skills deve ser refletida via `sync_docs --sync`.

## CI Docs-Sync Job

O job `docs-sync` no `ci.yml` roda:

1. `python scripts/sync_docs.py --analyze` (V2 stale-ref detector)
2. `python scripts/agents_tool.py --check` (schema validation) — **adicionado Sprint 11**

Falha em qualquer um bloqueia o job.

## Saneamento do Working Tree (Sprint 13)

```bash
# Uso diário (modo rápido, <2s)
python scripts/sanitize.py --execute --quick

# Completo (com prompts Y/N por categoria)
python scripts/sanitize.py --execute

# Auditoria semanal (só ver o que seria limpo)
python scripts/sanitize.py --dry-run

# Rollback do último --execute
python scripts/sanitize.py --rollback
```

**Regras de governança:**

1. **`--quick` ao final do dia** — limpa caches Python + wheels baixados manualmente
2. **`--dry-run` semanalmente (segunda)** — auditoria manual; idealmente antes de push
3. **Hook RESIDUE GUARD (pre-commit)** — bloqueia commit de `.whl`, `C?Usersericsf/`, apátridas, `data/audit/`, `data/skills_backup/`, `skills-lock.json`, `.archive/sanitize/`
4. **NUNCA colocar sanitize no pre-push** — manter push rápido (9 checks principais, rodando em paralelo)
5. **Snapshot antes de mutação irreversível** — `--rollback` restaura backup_personal do último `--execute`
6. **CI semanal dry-run** — workflow `sanitize-check.yml` falha se detectar lixo novo no working tree
7. **CI status check antes de push** — pre-push hook tenta `gh run list` (step 2/4, warn-only, timeout 15s). Se CI estiver vermelho, AVISA (não bloqueia — o push pode ser a correção). Se `gh` não estiver autenticado, AVISA. Responsabilidade do desenvolvedor: não pushar sobre CI vermelho sem ser a correção. Autenticar com `gh auth login` ou `GH_TOKEN` no `.env`.
