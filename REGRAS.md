# REGRAS.md — Ambiente, Hooks, Comandos

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
python --version    # deve ser 3.11+
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

4 steps existentes:
1. Working tree limpo
2. `audit_secrets --strict`
3. `ruff check .`
4. `mypy .`

**Add (Sprint 11)**: Roda `python scripts/agents_tool.py --check` antes de validar secrets. Falha bloqueia push.

### Resolução Automática de Python (.venv314)

O hook **sempre** usa `.venv314/Scripts/python.exe` (Windows) ou `.venv314/bin/python` (WSL), independente de quem invocou o git:

```python
# .githooks/pre-push
def _resolve_python() -> str:
    candidates = [
        REPO_ROOT / ".venv314" / "Scripts" / "python.exe",  # Windows
        REPO_ROOT / ".venv314" / "bin" / "python",           # WSL/Linux
    ]
    for c in candidates:
        if c.exists() and os.access(c, os.X_OK):
            return str(c)
    return sys.executable  # fallback apenas se .venv314 não existir
```

**Por quê?** `sys.executable` no hook resolves o Python que invocou o git → pode ser Python 3.11 global se você rodar `git` fora do venv. O `_resolve_python()` força o uso do venv → **garantia de paridade** com CI/Cloud.

**Saída do hook** (a 1ª linha mostra qual Python será usado):
```
  [python] usando venv: C:\Zerobond\Code\CustoDoce\.venv314\Scripts\python.exe
=== pre-push: validando...
```

Fallback via `sys.executable` só ocorre se `.venv314/` não existir — nesse caso o hook emite AVISO. **Recomendado**: rodar `pip install -r requirements.lock` em `.venv314` antes do push.

Opt-in Unit Tests: `set CI_LOCAL_UNIT=1` (cmd) ou `$env:CI_LOCAL_UNIT="1"` (ps).

Emergência: `git push --no-verify` (não recomendado).

## Scripts de Segurança

- `scripts/audit_secrets.py --strict` — varre histórico por chaves
- `scripts/install_hooks.sh` — instala/re-instala hooks (shell-based, via WSL)

## OpenCode Skills Strategy

Duas camadas:

| Camada | Localização | Propósito |
|--------|-------------|-----------|
| **Global** | `~/.config/opencode/skills/` | 17 skills universais |
| **Local** | `.opencode/skills/` | 7 overlays específicos CustoDoce |

### Skills Globais (17)

scraping-resilience, code-quality-pro, test-architect, api-design, code-review, debug-troubleshooting, docs-writer, git-workflow, github-actions, project-doc-sync, refactor-patterns, sql-optimizer, streamlit, telegram-bot, test-generation, humanizer, seo, ui-ux-pro-max.

### Overlays Locais (7)

telegram-bot, docs-writer, sql-optimizer, streamlit, api-design, github-actions, project-doc-sync.

## CI Docs-Sync Job

O job `docs-sync` no `ci.yml` roda:

1. `python scripts/sync_docs.py --analyze` (V2 stale-ref detector)
2. `python scripts/agents_tool.py --check` (schema validation) — **adicionado Sprint 11**

Falha em qualquer um bloqueia o job.
