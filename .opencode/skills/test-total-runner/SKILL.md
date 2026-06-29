---
name: test-total-runner
description: Run CustoDoce end-to-end test pipeline (lint + mypy + 11 phases) and produce JSON report
when_to_use: When the user asks for "rodar o teste total do sistema", "testTotalCoverage", "full pipeline test", "11-phase pipeline", "CI local mirror", or wants to know whether the repo is fully green locally before pushing.
location: "C:\\Zerobond\\Code\\CustoDoce"
---

# test-total-runner

The "always works" recipe for orchestrating the entire CustoDoce test pipeline locally.

## What it does

Drives 11 phases sequentially:

1. `ruff check .` — lint (zero warnings allowed)
2. `ruff format . --check` — formatting parity (optional)
3. `mypy .` — typecheck (zero errors)
4. `pytest tests/unit/ tests/schema/ -q` — deterministic unit + schema
5. `pytest tests/integration/ -q` — DB-real via RPC (mock)
6. `pytest tests/real/ -q` — real scrapers (slow)
7. `pytest tests/design/ -q` — CSS/structure
8. `scripts/sync_docs.py --check` — drift detection against pytest
9. `scripts/audit_secrets.py --strict` — secret scanner
10. `scripts/deploy_check.py` — live DB smoke
11. Clears the report cache (keeps last N=10 reports)

Each phase produces structured output written to `data/test_runs/coverage_<timestamp>.json`.

## When to invoke

- "rode o teste total" / "full pipeline test" / "CI local mirror"
- "o repo está verde?" / "tudo está passando local?"
- Before pushing (opt-in pre-push hook: `CI_LOCAL_UNIT=1`)
- After non-trivial commits (Sprint boundaries)
- When adding new modules or refactoring storage layer

## Invocation

```bash
python scripts/test_total_coverage.py                  # all phases
python scripts/test_total_coverage.py --skip-slow       # no integration/real
python scripts/test_total_coverage.py --out path.json   # custom report path
```

Returns exit code 0 if all phases PASS, 1 if any FAIL/ERROR/TIMEOUT.

## Outputs

- `data/test_runs/coverage_<timestamp>.json` — aggregated report (PASS/FAIL counts, per-phase timing, stdout tail per phase, git SHA, branch).
- stdout shows per-phase status flags in real time.

## Failure handling

When any phase reports `FAIL`:

1. Read the `stdout_tail` (last 800 chars) for the failing phase in the report.
2. If `pytest -m ...` fails, identify the failing test name and `python -m pytest tests/path::test -v` for diagnostic.
3. For sync_docs drift: `python scripts/sync_docs.py` (without `--check`) auto-corrects.
4. For `audit_secrets`: find the matched pattern, remove from repo, rotate the secret.
5. After fix, re-run `python scripts/test_total_coverage.py` to confirm.

## Memory Sync (Lição #11 reminder)

If you change test counts or module structure after running this script, update:

- `AGENTS.md` Status table (Sprint section)
- `tests/README.md` if you added test layers
- `docs/changelog.md` with the entry

Run `python scripts/sync_docs.py` (no flags) to regenerate AGENTS.md automatically.

## Self-healing context

The total pipeline also implicitly exercises `services/scraper_health.py`. If `scripts/heal_scrapers.py list-disabled` shows scrapers, validate via:

```bash
python scripts/heal_scrapers.py run-all --dry-run
python scripts/heal_scrapers.py failures "<name>" --days 30
```

## Related

- `.githooks/pre-push` — opt-in pre-push hook with `CI_LOCAL_UNIT=1`
- `.opencode/skills/test-total-runner/SKILL.md` — this skill
- `scripts/sync_docs.py` — source-of-truth auto-correction
- `services/scraper_health.py` — self-healing core (Lição #15)
- `AGENTS.md` Migrations #11 (Memory Sync) and #15 (self-healing required)
