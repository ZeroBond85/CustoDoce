---
name: doc-sync
description: >
  Run `python scripts/sync_docs.py` to keep AGENTS.md, README, API docs, page
  counters, and CI workflow lists in sync with actual code. Handles v1 (full
  regen) + v2 (heading-aware CURRENT blocks) sync. Dry-run safe.
---

# Doc Sync — Universal Pattern

## When to run

- **Before every push** (pre-push hook runs `--check --strict` automatically)
- After adding/renaming/removing a dashboard page
- After adding a new `services/*.py` module or changing public function names
- After adding/renaming/removing a `.github/workflows/*.yml`
- After changing test counts
- After changing AGENTS.md counters, README.md architecture, or `docs/api/*.md`
- **CI blocks merge** if `--check` exits 1

## Flags

| Flag | Effect |
|------|--------|
| `--dry-run` | Preview changes without modifying files |
| `--sync` | Apply changes live |
| `--check` | Exit 1 if drift detected (CI mode) |
| `--strict` | Scan ALL `.md` for stale patterns (slow) |
| `--strict --experimental` | Same, but with heading-aware classifier (fewer false positives) |
| `--dump-truth` | Print current truth JSON and exit |
| `--all` | Sync truth into every `{{CURRENT ...}}` block |
| `--no-intelligent` | Skip heading-aware filtering (match everything) |

## Workflow

```bash
# 1. Preview what will change
python scripts/sync_docs.py --dry-run

# 2. Apply
python scripts/sync_docs.py --sync

# 3. Check CI mode (exit 1 if out of sync)
python scripts/sync_docs.py --check

# 4. Full strict check (2-10s per file)
python scripts/sync_docs.py --check --strict

# 5. Strict with v2 classifier
python scripts/sync_docs.py --check --strict --experimental
```

## What sync_docs updates

| Target | Source of truth |
|--------|----------------|
| `README.md` | Timestamp + architecture section |
| `AGENTS.md` | Test counts, page list, services, workflows, lessons count |
| `docs/api/*.md` | Function signatures from `services/*.py` AST |
| `docs/skills.md` | Installed skills list |
| `docs/changelog.md` | Ordering validation |
| `docs/archive/CUSTO_DOCE_RAIO_X.md` | Timestamp |
| `{{CURRENT ...}}` blocks (v2) | Heading-aware stale ref replacement |

## Rules

- Always `--dry-run` first before `--sync` on production branches
- `--check` must pass in CI before merge
- Never edit timestamp-only lines manually — `--sync` overwrites them
- `--strict` audit on every `.md` in the repo; use `--experimental` to reduce noise
- Pre-push hook auto-runs `--check --strict` — if it fails, fix and re-push
