# REGRAS.md — Ambiente, Hooks, Comandos

> Ambiente de execução, hooks de git, comandos de rotina e configurações obrigatórias.
> Extraído de AGENTS.md original (seções "Ambiente", "Pre-commit/pre-push hooks", "OpenCode Skills Strategy").

## Ambiente: Escolha do Executor

| Tarefa | Executor | Motivo |
|--------|----------|--------|
| ruff, mypy, pytest (unit/schema) | **Windows** (PowerShell) | Nativo, sem overhead de WSL |
| Shell scripts (.sh) | **WSL (Debian)** | PowerShell/cmd quebra escapes |
| Git filter-branch, rebase | **WSL (Debian)** | PowerShell heredoc quebra `\` |
| Simular CI Linux (act, bash) | **WSL (Debian)** | GitHub Actions usa Linux |
| Playwright, scrapers reais, OCR | **WSL (Debian)** | Browser automation estável |
| Scripts de deploy, DB, SQL | **Windows** | python direto funciona |

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
