#!/usr/bin/env python3
"""Validate that .gitattributes forces LF on git hooks (regra mandatoria #17).

Hooks live in .githooks/ WITHOUT a file extension (e.g. pre-push, pre-commit).
With core.autocrlf=true on Windows, Git converts LF->CRLF on checkout, and the
WSL mount reads the raw C: bytes -> the shebang `#!/usr/bin/env python3.14\r`
breaks (`env: 'python3.14\r': No such file or directory`), blocking every push.

This check fails HARD if any hook path pattern is missing `eol=lf` in
.gitattributes, so the regression from 2026-07-19 can never silently return.

Exit code 1 = misconfigured (CI must block merge).
"""
from __future__ import annotations

import sys
from pathlib import Path

REQUIRED_PATTERNS = (".githooks/*", ".git/hooks/*")
GITATTRIBUTES = Path(".gitattributes")


def _parse_eol_rules(text: str) -> dict[str, str]:
    """Map glob pattern -> eol value (from lines like `*.py eol=lf`)."""
    rules: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pattern = parts[0]
        for attr in parts[1:]:
            if attr.startswith("eol="):
                rules[pattern] = attr.split("=", 1)[1]
    return rules


def main() -> int:
    if not GITATTRIBUTES.exists():
        print(f"[FAIL] {GITATTRIBUTES} not found")
        return 1

    rules = _parse_eol_rules(GITATTRIBUTES.read_text(encoding="utf-8"))

    missing: list[str] = []
    for pattern in REQUIRED_PATTERNS:
        eol = rules.get(pattern)
        if eol != "lf":
            missing.append(pattern)

    if missing:
        print("[FAIL] .gitattributes must force eol=lf on git hooks (regra #17)")
        for m in missing:
            print(f"  Missing/incorrect: '{m}' (found eol={rules.get(m, '<none>')})")
        print("  Fix: add `.githooks/* eol=lf` and `.git/hooks/* eol=lf` to .gitattributes")
        return 1

    print("[OK] .gitattributes forces eol=lf on .githooks/* and .git/hooks/*")
    return 0


if __name__ == "__main__":
    sys.exit(main())
