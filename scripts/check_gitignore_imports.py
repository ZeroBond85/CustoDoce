# mypy: ignore-errors
#!/usr/bin/env python3
"""
Check if any staged Python files import modules that are gitignored.
Prevents ModuleNotFoundError in CI when a file exists locally but isn't tracked.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GIT = shutil.which("git") or "git"


def get_staged_python_files() -> list[Path]:
    """Get staged Python files."""
    result = subprocess.run(
        [GIT, "diff", "--cached", "--name-only", "--diff-filter=ACM", "*.py"],
        cwd=REPO_ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        return []
    return [REPO_ROOT / f for f in result.stdout.strip().splitlines() if f]


def is_gitignored(path: Path) -> bool:
    """Check if a path is gitignored."""
    result = subprocess.run(
        [GIT, "check-ignore", "-v", str(path.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT, capture_output=True, text=True
    )
    return result.returncode == 0


def find_imports_in_file(filepath: Path) -> list[str]:
    """Extract all 'from X import' and 'import X' statements from a Python file."""
    imports = []
    try:
        content = filepath.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("from ") and " import " in stripped:
                # from X.Y import Z
                mod = stripped.split(" import ")[0].replace("from ", "").strip()
                imports.append(mod)
            elif stripped.startswith("import "):
                # import X, Y
                mods = stripped.replace("import ", "").split(",")
                for m in mods:
                    m = m.strip().split(" as ")[0].strip()
                    if m:
                        imports.append(m)
    except Exception:
        pass
    return imports


def module_to_path(mod: str) -> Path | None:
    """Convert module name to file path."""
    parts = mod.split(".")
    if parts[0] in ("scripts", "services", "parsers", "scrapers", "dashboard", "admin", "telegram_bot", "tests", "config"):
        return REPO_ROOT / Path(*parts).with_suffix(".py")
    return None


def main() -> int:
    staged = get_staged_python_files()
    if not staged:
        return 0

    issues = []
    for f in staged:
        for mod in find_imports_in_file(f):
            path = module_to_path(mod)
            if path and path.exists() and is_gitignored(path):
                issues.append(f"  {f.relative_to(REPO_ROOT)} -> imports '{mod}' (gitignored: {path.relative_to(REPO_ROOT)})")

    if issues:
        print("🚨 COMMIT BLOQUEADO: imports de arquivos gitignored detectados.")
        print("")
        print("Os seguintes arquivos staged importam módulos que estão no .gitignore:")
        for issue in issues:
            print(issue)
        print("")
        print("Acoes:")
        print("  - Remova o arquivo do .gitignore (se for necessário no CI)")
        print("  - Ou refatore o import para não depender do arquivo ignorado")
        print("  - Ou use 'git commit --no-verify' para emergência (NÃO recomendado)")
        print("")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())