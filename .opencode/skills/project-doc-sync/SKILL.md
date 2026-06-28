---
name: project-doc-sync
description: "extends docs/sync_docs behavior for CustoDoce doc set conventions."
---

# project-doc-sync — CustoDoce overlay

This overlay complements `scripts/sync_docs.py` — a real script in this repo. Universal sync patterns (when to run, dry-run vs apply, CI integration, hook) live in `~/.config/opencode/skills/project-doc-sync/SKILL.md`. This overlay documents CustoDoce-specific scripts that the sync covers.

## What the script does
```bash
# Preview
python scripts/sync_docs.py --dry-run

# Apply
python scripts/sync_docs.py

# Strict CI mode (exit 1 if drifted)
python scripts/sync_docs.py --check
```

## What gets updated
| Target | Source of truth |
|--------|----------------|
| `AGENTS.md` test counts | `pytest tests/unit tests/schema --collect-only -q` |
| `AGENTS.md` page list | `dashboard/components/layout.py::PAGES` |
| `AGENTS.md` services list | `services/*.py` — public functions |
| `AGENTS.md` workflow list | `ls .github/workflows/*.yml` |
| `README.md` architecture diagram | Hand-curated; sync only timestamps |
| `docs/api/*.md` | Validated to exist (non-empty) |

## What the script does NOT do (be aware)
- ❌ Doesn't auto-generate new docs files.
- ❌ Doesn't modify code (`scrapers/`, `services/`, `dashboard/`, `tests/`).
- ❌ Doesn't fix broken links — only validates that internal `#anchor` targets exist.
- ❌ Doesn't commit; you commit after.

## When CI is mandatory
Run `--check` mode on:
- Before merge to `develop` or `main`.
- After adding/removing/renaming a page.
- After adding a new script under `scripts/`.
- After dependency changes (`requirements.txt` or `pyproject.toml`).

See `docs-writer` overlay for the full doc-set ownership map and conventions.

## How skill-writers should treat this overlay
- Don't duplicate the global skill content here. Reference back: "see `~/.config/opencode/skills/project-doc-sync/SKILL.md` for universal sync patterns."
- Keep this overlay's table of "what gets updated" in sync with the actual script's behavior. If the script grows new update targets, add them here.
