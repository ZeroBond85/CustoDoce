"""
Validate MD Timestamps — CI gate.

Falha se:
1. Algum .md não tem timestamp padronizado (> Última atualização/revisão: ...)
2. Timestamp tem mais de N dias (default: 14, configurável via --max-age-days)

Ignora: .git, .venv, node_modules, __pycache__, lib64
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

_TIMESTAMP_PAT = re.compile(
    r"> Última (atualização|revisão): (\d{4}-\d{2}-\d{2}) \d{2}:\d{2} UTC"
)

_SKIP_DIRS = {".git", ".venv", ".venv314", "node_modules", "__pycache__", "lib64", ".pytest_cache", ".opencode", ".agent"}

# Arquivos que têm sistemas próprios de data (changelog tem entries)
_EXCLUDE_FILES = {"docs/changelog.md", "docs/skills.md", "AGENTS.md"}


def validate(root: Path, max_age_days: int = 14) -> list[str]:
    """Varre todos .md e retorna lista de issues."""
    issues: list[str] = []

    for md_file in root.rglob("*.md"):
        rel = md_file.relative_to(root)
        if any(skip in md_file.parts for skip in _SKIP_DIRS):
            continue
        if str(rel).replace("\\", "/") in _EXCLUDE_FILES:
            continue

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
        default=14,
        help="Max age in days (default: 14)",
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
