---
name: docs-writer
description: "extends global docs-writer with CustoDoce documentation conventions."
---

# docs-writer — CustoDoce overlay

Universal doc patterns (README, API doc, ADR, Runbook, Decision Panel) live in `~/.config/opencode/skills/docs-writer/SKILL.md`. This overlay adds CustoDoce doc-set conventions.

## Doc-set map for this project
| File | Update when… | Owner |
|------|--------------|-------|
| `README.md` | Public-facing features change | Maintainer |
| `AGENTS.md` | Stack, project structure, or coin-flip conventions change | Maintainer (committed) |
| `docs/adr/NNN-*.md` | Durable architectural decision taken | Maintainer |
| `docs/runbooks/*.md` | Operational symptom → fix flow added/changed | SRE-minded maintainer |
| `supabase/consolidated_migration.sql` | Schema or RPC changes | DB changes only |
| `CHANGELOG.md` | Release-level change | Auto via `release.yml` |

## ADR numbering
- Sequentially numbered (`001`, `002`, …) — never reuse.
- Status field must be one of: `Proposed` / `Accepted` / `Deprecated` / `Superseded by ADR-NNN`.
- Reference relevant issue/PR in footer.

## Runbook format (CustoDoce flavor)
All runbooks follow the global template, plus:
- Tag severity: `SEV-1` (data corruption, loss, auth bypass) / `SEV-2` (degraded operation, single store offline) / `SEV-3` (cosmetic).
- Always include **escalation path** (which file or which sibling runbook).
- If the runbook cites a specific GitHub Action, name the workflow file (e.g. `scrape.yml`).

## Project-aware language conventions
- Use Portuguese for user-facing copy, English for code, comments, commit messages (matches `AGENTS.md` rule 10).
- Project name "CustoDoce" is one word, capital C capital D, no accents.
- Ingredient canonical names live in `config/ingredients.yaml` — always reference that file when writing copy.

## Tooling hooks
- `scripts/sync_docs.py` keeps `AGENTS.md` test counts, page lists, workflows lists in sync. Run before opening any PR that adds a test/page/workflow.
- `.github/hooks/pre-commit` warns if you modified `.py` files without touching `CHANGELOG.md`.
