# REGRAS.md — Ambiente, Hooks, Comandos
> Última atualização: 2026-07-17 04:28 UTC

> Ambiente de execução, hooks de git, comandos de rotina e configurações obrigatórias.
> Extraído de AGENTS.md original (seções "Ambiente", "Pre-commit/pre-push hooks", "OpenCode Skills Strategy").

## Ambiente: Escolha do Executor

| Tarefa | Executor | Motivo | Tooling |
|--------|----------|--------|---------|
| ruff, mypy, pytest (unit/schema) | **Windows** | Latência zero, sem overhead de WSL | `.venv314` |
| Dashboard (Streamlit) | **Windows** | Renderização e rede local nativa | `.venv314` |
| Scripts de deploy, DB, SQL | **Windows** | Python direto via RPC/HTTPS | `.venv314` |
| Shell scripts (.sh), Git complexo | **WSL (Debian)** | PowerShell quebra escapes/heredocs | Bash |
| `git push` com pre-push completo | **WSL (Debian)** | pre-push roda `sync_docs`, `ci_local`, `schema_mocks` — todas as deps no Python 3.14.6 nativo (`/usr/local/bin/python3.14`) | Python 3.14.6 NATIVO (sem conda) |
| Simular CI Linux, Scrapers Reais | **WSL (Debian)** | Idêntico ao GitHub Actions (Ubuntu) | Python 3.14.6 NATIVO |
| Playwright, OCR (Tesseract) | **WSL (Debian)** | Browser automation e dependências SO | Python 3.14.6 NATIVO |
| Testtes E2E / Visual | **WSL (Debian)** | Estabilidade do Chromium Headless | Python 3.14.6 NATIVO |
| **Gerar lock files (`pip-compile`)** | **WSL (Debian)** | CI roda em Ubuntu Linux; Windows inclui `colorama`/`tzdata` que não existem no Linux → drift | Python 3.14.6 NATIVO + `PIP_EXTRA_INDEX_URL` |

### ⚠️ CRLF vs LF: Toda Geração de Docs Roda no WSL

O `sync_docs.py` gera arquivos `.md` via `write()` do Python. No Windows, `write()` usa CRLF. O `.gitattributes` exige `eol=lf` para `*.md`. Isso causa:

- **pre-commit bloqueia**: detecta CRLF em staged files
- **Churn de diff**: scripts reescrevem o arquivo, mudam line endings, diff poluído

**Regra:** Para qualquer comando que gere/modifique arquivos de documentação, use **WSL**:

```bash
# WSL - CRLF nunca acontece
cd /mnt/c/Zerobond/Code/CustoDoce
python scripts/sync_docs.py              # gera LF nativamente
git add docs/ && git commit              # pre-commit feliz
```

**Exceção:** Edição manual via `edit` tool no Windows é segura — a tool usa LF preservando o existente.

### ⚠️ Lei do Ambiente (Anti-Fricção)
1. **Proibido "Misturar" Shells**: Não execute `wsl bash -c '...'` para tarefas que podem rodar em Python no Windows. Use WSL apenas para dependências de SO.
2. **Isolamento de Paths**:
   - Windows $\rightarrow$ `C:\Zerobond\Code\CustoDoce`
   - WSL $\rightarrow$ `/mnt/c/Zerobond/Code/CustoDoce`
   - Nunca passe caminhos de Windows para o Bash sem converter para o formato `/mnt/c/`.
3. **Default Python**:
   - Windows: `.venv314` (PowerShell)
    - WSL: Python 3.14.6 NATIVO (`/usr/local/bin/python3.14`, Bash)
4. **Paridade de Versões (Obrigatório — expandida)**:
   - **Python local (Windows/WSL) DEVE ser igual ao CI (GitHub Actions) e Cloud (Streamlit)**.
   - **Versões obrigatórias**: `pyproject.toml` (target-version), `runtime.txt`, `.devcontainer/devcontainer.json`, workflows (`PYTHON_VERSION`), e `pyproject.toml` (mypy `python_version`) — todos Python **3.14.x**.
   - **Lock files (requirements-*.lock)** são a única fonte de verdade. `requirements.txt` e `requirements.lock` são cópias do `requirements-test.lock`. Toda instalação via `pip install` em workflow DEVE usar `package==X.Y.Z` (nunca sem pin). (Geração: ver item 5 — WSL obrigatório.)
   - **Actions @tags**: Consistentes em TODOS os workflows: `checkout@v7`, `setup-python@v6`, `cache@v6`, `upload-artifact@v7`. Qualquer outlier bloqueia merge.
   - **System deps (tesseract/poppler/playwright)**: Instalados com mesmos comandos em CI, WSL e devcontainer. `packages.txt` é lista canônica; alterações refletidas em todos os locais.
   - **.devcontainer**: Deve espelhar o Python target do projeto e instalar via lock files (`requirements-prod.lock`), não `requirements.txt`.
   - **Verificação**: `python scripts/check_environment_parity.py` (roda no CI job `lint`, falha HARD em divergência).
   - **Qualquer discrepância bloqueia merge** — CI valida no alvo real.
      - **Drift de WSL**: Checar periodicamente: `wsl bash -c 'python --version && /usr/local/bin/python3.14 -m pip --version'`
5. **WSL = Linux Canônico (Anti-Drift de Plataforma)**: Toda tarefa que depende de **resolver dependências em ambiente Linux** deve rodar no WSL com Python 3.14.6 NATIVO (`/usr/local/bin/python3.14`) — NUNCA no Windows. O CI (GitHub Actions) roda em Ubuntu; o WSL é nosso Ubuntu local. Isso previne drift silencioso de pacotes condicionais de plataforma (`colorama`, `tzdata`, etc.) que existem no Windows mas não no Linux. Tarefas obrigatórias em WSL:
   - **`pip-compile`** (geração de lock files): `PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu pip-compile --allow-unsafe --output-file=requirements-prod.lock requirements-prod.in`
   - **`pip install -r requirements-test.lock`** (quando testar integração/CI locally)
   - **Playwright, OCR, scrapers** (browser automation)
   - **`sync_docs.py`** (evitar CRLF, ver seção CRLF acima)
   - Qualquer `pip install` que precise de pacotes com `manylinux` wheels
   - **Exceção**: Instalação de deps puras Python (ruff, mypy) pode rodar no Windows sem drift.


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

## Pre-commit Hook (`.githooks/pre-commit`) — 11 camadas

1. **SECRET GUARD**: BLOQUEIA chave de API em staged
1.5 **GITIGNORE IMPORTS**: BLOQUEIA staged que importa itens gitignorados
1.7 **DETECT-SECRETS**: BLOQUEIA se detect-secrets encontrar segredo
1.8 **RUFF LINT**: BLOQUEIA se ruff encontrar erros em .py staged
2. **DOC SYNC**: BLOQUEIA se código mudou sem docs (YES bypass / A auto-sync)
3. **SIZE GUARD**: BLOQUEIA arquivo >100MB staged (GitHub rejeita)
4. **DOC WATCHDOG**: AVISO leve sobre outros docs
5. **AGENTS SCHEMA**: BLOQUEIA se AGENTS.md não passar em `agents_tool.py --check` (valida schema + LESSONS.md + REGRAS.md)
6. **SKILL DRIFT**: BLOQUEIA se `.opencode/skills/` mudou sem `sync_docs --check` alinhado
7. **RESIDUE GUARD**: BLOQUEIA commit com artefatos de runtime no stage
8. **CRLF GUARD**: BLOQUEIA arquivos texto com CRLF (previne churn de line-ending)

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

**🚫 Windows — push NUNCA deve ser rotina aqui**: O pre-push **não funciona completamente** no Windows porque `sync_docs.py` importa todo o projeto (exige todas as deps instaladas) e deixa a working tree dirty (auto-fix de docstrings), barrando o push de forma falsa. **O push com validação completa (pre-commit + pre-push) é OBRIGATÓRIO em WSL com Python 3.14.6 NATIVO (`/usr/local/bin/python3.14`)** — este é o ambiente canônico e a ÚNICA via correta para push de verdade.

- **Regra mandatória**: Para qualquer push real, usar **WSL** (Python 3.14.6 nativo): `git add . && git commit` (hooks passam) e `python scripts/git_push.py` (PATH de `gh`/`git` já vem do bash do WSL). Nunca tratar o Windows como ambiente de push.
- **Exceção (apenas emergência, nunca rotina)**: Se for estritamente necessário pushar do Windows, usar `git push --no-verify` (a regra documentada) — mas o pre-commit/pre-push NÃO rodou, então a validação fica a cargo do CI. Isso NÃO substitui o fluxo WSL.
- **`sync_docs` auto-fix no Windows**: se o hook modificar `docs/api/*` e sujar a tree, commitar essas mudanças geradas separadamente (não são do código) — elas são docstrings auto-geradas, não contorno.

**⚠️ PATH de `gh`/`git` no WSL**: Em WSL o PATH do bash já traz `gh`/`git`. No Windows (apenas emergência), `scripts/git_push.py` injeta `C:\Program Files\GitHub CLI` + `C:\Program Files\Git\bin` via `_ensure_bin_path()` ANTES do `git push` para evitar `FileNotFoundError` falso. Se `gh` der `FileNotFound`, é problema de **AMBIENTE** (corrigir PATH), nunca contornar com `--no-verify` para esconder erro. (Ver `LESSONS.md` #80)

**Otimização (Fase 1)**: checks independentes rodam em paralelo; wall-time ≈ max(ci_local, demais) em vez de soma. `audit_secrets` escopado a commits outgoing. Rede (`gh`, `pip-audit`) tem timeout.

### Resolução Automática de Python

O hook `pre-push` resolve o Python na seguinte ordem (Python NATIVO 3.14.6 do WSL é a fonte canônica; miniconda foi removido):

1. **Env var `CUSTODOCE_PYTHON`** — override explícito (ex: `export CUSTODOCE_PYTHON=/usr/local/bin/python3.14`).
2. **`/usr/local/bin/python3.14`** — Python NATIVO 3.14.6 (compilado de tarball oficial, fora do repo).
3. **`~/bin/python3.14`** — symlink do usuário → 3.14.6 nativo.
4. **`.venv314/Scripts/python.exe`** — venv Windows nativo (fallback, dentro do repo).
5. **`.venv314/bin/python`** — venv Linux/WSL nativo (fallback, dentro do repo).
6. **`sys.executable`** — fallback (com AVISO se nenhum Python com deps existe).

```python
# .githooks/pre-push
def _resolve_python() -> str:
    explicit = os.environ.get("CUSTODOCE_PYTHON")
    if explicit and Path(explicit).exists() and os.access(explicit, os.X_OK):
        return explicit
    candidates = [
        Path("/usr/local/bin/python3.14"),
        Path.home() / "bin" / "python3.14",
        REPO_ROOT / ".venv314" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv314" / "bin" / "python",
    ]
    for c in candidates:
        if c.exists() and os.access(c, os.X_OK):
            return str(c)
    return sys.executable  # fallback (AVISO)
```

**Por quê?** O WSL roda Python 3.14.6 compilado de tarball oficial em `/usr/local/bin/python3.14` (não o 3.13 do `/usr/bin` que é do apt/dpkg). `python`/`python3` do usuário apontam via `~/bin` symlinks para 3.14.6. O `_resolve_python()` força o uso do 3.14.6 nativo → **paridade total** com CI/Cloud.

**Output do hook** mostra qual Python foi resolvido na 1ª linha:
```
  [python] usando: /usr/local/bin/python3.14
=== pre-push: validando...
```

**Cross-platform**: mesmo hook funciona em Windows PowerShell, WSL bash, e macOS zsh. Cada plataforma tem seu fallback canônico:
- **Windows**: `.venv314/Scripts/python.exe` (Python 3.14.6)
- **WSL**: `/usr/local/bin/python3.14` (Python 3.14.6 NATIVO — sem conda)
- **macOS**: `/usr/local/bin/python3.14` (similar)

Fallback `sys.executable` só ocorre se nenhum Python com deps existir — nesse caso o hook emite AVISO. CI: 9 workflows Python 3.14 (single source of truth).

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
