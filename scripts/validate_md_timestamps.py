"""
Validate MD Timestamps — CI gate.

Falha se:
1. Algum .md (policy TIMESTAMP/TIMESTAMP_PROTECTED) não tem timestamp
   padronizado (> Última atualização/revisão: ...)
2. Timestamp tem mais de N dias (default: 30, configurável via --max-age-days)

Respeita doc_sync_policy: arquivos que o sync NUNCA mantém (IMMUTABLE,
SNAPSHOT_FROZEN, SNAPSHOT_DERIVED_LIVE, SNAPSHOT_REFERENCE_LIVE) são
ignorados — não faz sentido exigir freshness de docs imutáveis/congelados.

Ignora: .git, .venv*, node_modules, __pycache__, lib64
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# `python scripts/validate_md_timestamps.py` põe scripts/ no sys.path, não o
# root — necessário para `import scripts.doc_sync_policy`.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.doc_sync_policy import DocPolicy, policy_for  # noqa: E402

_TIMESTAMP_PAT = re.compile(
    r"> Última (atualização|revisão): (\d{4}-\d{2}-\d{2}) \d{2}:\d{2} UTC"
)

_SKIP_DIRS = {
    ".git", ".venv", ".venv314", ".venv_wsl", ".venv314wsl",
    "node_modules", "__pycache__", "lib64", ".pytest_cache",
    ".opencode", ".agent", "data",
}

# Arquivos que têm sistemas próprios de data (changelog tem entries)
_EXCLUDE_FILES = {"docs/changelog.md", "docs/skills.md", "AGENTS.md"}


def validate(root: Path, max_age_days: int = 30) -> list[str]:
    """Varre todos .md e retorna lista de issues."""
    _POLICY_SKIP = {
        DocPolicy.IMMUTABLE,
        DocPolicy.SNAPSHOT_FROZEN,
        DocPolicy.SNAPSHOT_DERIVED_LIVE,
        DocPolicy.SNAPSHOT_REFERENCE_LIVE,
    }

    issues: list[str] = []

    for md_file in root.rglob("*.md"):
        rel = md_file.relative_to(root)
        if any(skip in md_file.parts for skip in _SKIP_DIRS):
            continue
        if str(rel).replace("\\", "/") in _EXCLUDE_FILES:
            continue

        # Arquivos que o sync nunca mantém não devem exigir freshness.
        try:
            if policy_for(rel) in _POLICY_SKIP:
                continue
        except Exception:
            pass

        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        m = _TIMESTAMP_PAT.search(content)
        if not m:
            issues.append(f"{rel}: missing timestamp")
            continue

        label = m.group(1)
        date_str = m.group(2)
        try:
            ts_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
            delta = datetime.now(UTC) - ts_date
            if delta.days > max_age_days:
                issues.append(
                    f"{rel}: timestamp is {delta.days} days old "
                    f"(max {max_age_days}) — label='{label}', date={date_str}"
                )
        except ValueError:
            issues.append(f"{rel}: invalid timestamp date: {date_str}")

    return issues


def main():
    parser = argparse.ArgumentParser(description="Validate MD timestamps are fresh")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=30,
        help="Max age in days (default: 30)",
    )
    parser.add_argument(
        "--root",
        type=str,
        default=".",
        help="Project root directory",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    issues = validate(root, max_age_days=args.max_age_days)

    if issues:
        print(f"[FAIL] Timestamp issues found: {len(issues)}")
        for i in issues:
            print(f"  - {i}")
        sys.exit(1)
    else:
        print(f"[OK] All {args.max_age_days} .md timestamps are fresh")
        sys.exit(0)


if __name__ == "__main__":
    main()
