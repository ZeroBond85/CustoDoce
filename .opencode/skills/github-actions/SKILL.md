---
name: github-actions
description: "extends global github-actions with the 14 CustoDoce workflows + free-tier budget."
---

# github-actions — CustoDoce overlay

Universal GitHub Actions patterns (triggers, jobs, caching, matrices, secret handling, reusable workflows, antipatterns) are in `~/.config/opencode/skills/github-actions/SKILL.md`. This overlay documents CustoDoce's specific 14-workflow setup.

## The 14 workflows

| File | Trigger | Purpose | Minutes/run (avg) |
|------|---------|---------|--------------------|
| `scrape.yml` | Cron weekdays 00:00 UTC + workflow_dispatch | Collect + normalize + upsert prices | ~8 |
| `scrape-reusable.yml` | workflow_call (scrape/on_demand/heal) + dispatch | Reusable scraper body (4 jobs: setup→scrape→macos→finalize) | ~15 |
| `ci.yml` | PR + push (path-filtered) to `master` + dispatch | lint→typecheck→docs→matcher→unit→integration→deploy-check→e2e→real | ~6 |
| `ci-e2e-only.yml` | workflow_dispatch | E2E smoke only (fast) | ~10 |
| `e2e.yml` | Monthly cron (1st, 10am UTC) + dispatch | Playwright e2e + visual regression + cloud smoke | ~60 |
| `backup.yml` | Weekly cron (Sun 8am UTC) + dispatch | RPC backup (`rpc_backup.py`) to release artifact | ~3 |
| `restore-test.yml` | workflow_run (após Backup success) | Restore backup to ephemeral service, smoke test | ~10 |
| `on_demand_scrape.yml` | repository_dispatch + workflow_dispatch | Manual scraper trigger for one store | ~2 |
| `heal-scrapers.yml` | Monthly cron (1st, 00:00 UTC) | Self-healing of failed scrapers (mode: heal) | ~4 |
| `skills-maintenance.yml` | Monthly cron (1st, 9am UTC) + dispatch + PR | Skills check/validate | ~3 |
| `dependency-audit.yml` | Monthly cron (1st, 9am UTC) + dispatch + push/PR requirements* | pip-audit + deptry + licenses + lock-validation | ~5 |
| `sanitize-check.yml` | Weekly cron (Mon 12pm UTC) + dispatch | Sanitize check (dry-run) | ~3 |
| `test_store_recovery.yml` | workflow_dispatch | Store recovery test (single/full stores) | ~5 |
| `teste_full_manual.yml` | workflow_dispatch | Full manual test suite (11 jobs, ~55min) | ~55 |

> **Nota**: `bench-ocr.yml` e `probe-antibot.yml` foram planejados mas NUNCA criados. Não adicionar.

## Free-tier math (2000 min/month)
- Scrape: 5 runs/week × 15 min × 4.3 = **~320 min**
- CI: ~25 PRs/pushes/month × 6 min = **150 min**
- E2E: 1/month × 60 min = **60 min**
- Backup: 4/month × 3 min = **12 min**
- Restore-test: 4/month × 10 min = **40 min**
- Sanitize: 4/month × 3 min = **12 min**
- On-demand: ~5/month × 2 min = **10 min**
- **Total: ~604 min/month** (well below 2000 limit)

> macOS runners (job `scrape-macos`) são gratuitos apenas em repositórios PÚBLICOS.

## Shared environment
```yaml
env:
  PYTHON_VERSION: '3.14.6'
  PYTHONUNBUFFERED: '1'
  PIP_EXTRA_INDEX_URL: https://download.pytorch.org/whl/cpu
  PIP_NO_WARN_YANKED: 1
  SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
  SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
```
All workflows must inherit `PYTHON_VERSION` at workflow-level (don't hardcode `'3.14.6'` per step).

## Setup Python pattern
Não existe reuso via `_setup-python.yml` — cada workflow usa `actions/setup-python@v6` direto:
```yaml
- uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6
  with:
    python-version: ${{ env.PYTHON_VERSION }}
    cache: 'pip'
    cache-dependency-path: requirements-prod.lock
```

## Actions versions canônicas (SHA-pinned)
| Action | Versão | SHA |
|--------|--------|-----|
| `actions/checkout` | v7 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/setup-python` | v6 | `ece7cb06caefa5fff74198d8649806c4678c61a1` |
| `actions/cache` | v6 | `55cc8345863c7cc4c66a329aec7e433d2d1c52a9` |
| `actions/upload-artifact` | v7 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` |
| `softprops/action-gh-release` | v3 | `3d0d9888cb7fd7b750713d6e236d1fcb99157228` |

Qualquer outlier bloqueia merge (AGENTS.md regra 10).

## Playwright no scrape-reusable
- Versão controlada via `env.PW_VERSION` (hoje `1.62.0`), sincronizada com `requirements-test.lock`.
- Cache key: `${{ runner.os }}-pw-${{ env.PW_VERSION }}-${{ hashFiles('requirements-prod.lock') }}`.

## CustoDoce-specific antipatterns
- ❌ Running the real scraper suite on every PR (budget exhaustion).
- ❌ Calling Playwright without `actions/setup-python`'s cached browsers (4-6 min extra per run).
- ❌ Hard-coding `python-version` per step (always use `${{ env.PYTHON_VERSION }}`).
- ❌ Job sem `timeout-minutes` (referência: 60 min upper bound, exigido em regra de review).
- ❌ Passar secrets parciais a um caller do `scrape-reusable.yml` (heal/scrape/on_demand devem passar TODOS os secrets que o modo exige).
- ❌ `set-output` (usar `$GITHUB_OUTPUT`) e `save-state` (usar `$GITHUB_STATE`).

## Required for new workflow additions
1. Update `AGENTS.md` manually (or run `scripts/sync_docs.py` later).
2. Add to the workflow table above.
3. Recompute the free-tier math — flag if total exceeds 1500 min.
4. Add `timeout-minutes` (default upper bound 60).