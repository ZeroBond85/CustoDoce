---
name: github-actions
description: "extends global github-actions with the 7 CustoDoce workflows + free-tier budget."
---

# github-actions — CustoDoce overlay

Universal GitHub Actions patterns (triggers, jobs, caching, matrices, secret handling, reusable workflows, antipatterns) are in `~/.config/opencode/skills/github-actions/SKILL.md`. This overlay documents CustoDoce's specific 7-workflow setup.

## The 7 workflows

| File | Trigger | Purpose | Minutes/run (avg) |
|------|---------|---------|--------------------|
| `scrape.yml` | Cron 2×/day + workflow_dispatch | Collect + normalize + upsert prices | ~8 |
| `ci.yml` | PR + push to main | Lint → Typecheck → unit → integration → deploy-check | ~6 |
| `e2e.yml` | Biweekly schedule (cron) | Playwright e2e + visual regression | ~60 |
| `backup.yml` | Weekly cron (Sunday 02:00 UTC) | `pg_dump` to release artifact | ~3 |
| `restore-test.yml` | Monthly cron (1st) | Restore backup to ephemeral service, smoke test | ~10 |
| `deploy-staging.yml` | Push to `develop` branch | Sync prod schema/data → staging | ~12 |
| `on_demand_scrape.yml` | workflow_dispatch | Manual scraper trigger for one store | ~2 |

## Free-tier math (2000 min/month)
- Scrape: 2 runs/day × 8 min × 30 days = **480 min**
- CI: ~25 PRs/month × 6 min = **150 min**
- E2E: 2/month × 60 min = **120 min**
- Backup: 4/month × 3 min = **12 min**
- Restore-test: 1/month × 10 min = **10 min**
- Staging deploy: ~3/month × 12 min = **36 min**
- On-demand: ~5/month × 2 min = **10 min**
- **Total: ~818 min/month** (well below 2000 limit)

## Shared environment
```yaml
env:
  PYTHON_VERSION: '3.13'
  PYTHONUNBUFFERED: '1'
  SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
  SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
```
All workflows must inherit this at workflow- or job-level. Don't redefine per-step.

## Reusable workflow
- `.github/workflows/_setup-python.yml` (job named `setup-python`) is reusable, resolves the exact `requirements*.txt` set, and caches pip + Hugging Face models + Playwright browsers.
- Any new workflow that runs tests should call it:
  ```yaml
  jobs:
    test:
      uses: ./.github/workflows/_setup-python.yml
      with:
        python-version: '3.13'
  ```

## CustoDoce-specific antipatterns
- ❌ Running the real scraper suite on every PR (budget exhaustion).
- ❌ Calling Playwright without `actions/setup-python`'s cached browsers (4-6 min extra per run).
- ❌ Hard-coding `python-version` per step (always use `${{ env.PYTHON_VERSION }}`).
- ❌ Adding `bash` actions in jobs that should stay Windows-compatible for cross-project skill compatibility.

## Required for new workflow additions
1. Update `AGENTS.md` manually (or run `scripts/sync_docs.py` later).
2. Add to the workflow table above.
3. Recompute the free-tier math — flag if total exceeds 1500 min.
4. Add `timeout-minutes` (default upper bound 60).
