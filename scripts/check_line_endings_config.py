#!/usr/bin/env python3
"""Check core.autocrlf is correct for the current platform.

Windows: must be 'input' (with comprehensive .gitattributes eol=lf) or 'true' (legacy).
WSL/Linux: must be 'false' or 'input'.

Exits with code 1 if misconfigured.
"""
import os
import subprocess
import sys


def _is_wsl() -> bool:
    return "microsoft" in (os.uname().release.lower() if hasattr(os, "uname") else "")


def _get_autocrlf() -> str:
    r = subprocess.run(
        ["git", "config", "core.autocrlf"],
        capture_output=True, text=True, check=False,
    )
    return r.stdout.strip().lower() if r.stdout else ""


def _has_comprehensive_gitattributes() -> bool:
    """Check if .gitattributes has explicit eol=lf for key patterns."""
    ga_path = ".gitattributes"
    if not os.path.exists(ga_path):
        return False
    with open(ga_path, encoding="utf-8") as f:
        content = f.read()
    # Check for explicit eol=lf on main patterns (flexible whitespace)
    import re
    required_patterns = [
        r"\*\.\s*py\s+eol=lf",
        r"\*\.\s*md\s+eol=lf",
        r"\.githooks/\*\s+eol=lf",
    ]
    return all(re.search(pat, content) for pat in required_patterns)


def main():
    autocrlf = _get_autocrlf()
    on_windows = sys.platform == "win32"
    on_wsl = on_windows is False and _is_wsl()
    has_gattr = _has_comprehensive_gitattributes()

    if on_windows:
        # Modern: input with .gitattributes; Legacy: true without
        valid = ("input", "true") if has_gattr else ("true",)
        if autocrlf not in valid:
            expected = "'input' (com .gitattributes completo) ou 'true' (legado)"
            if has_gattr:
                expected = "'input' (com .gitattributes completo)"
            print(f"[FAIL] Windows: core.autocrlf='{autocrlf}', esperado {expected}")
            print("  Fix: git config --local core.autocrlf input")
            sys.exit(1)
        print(f"[OK] Windows: core.autocrlf='{autocrlf}' (gitattributes={'completo' if has_gattr else 'incompleto'})")
    elif on_wsl:
        if autocrlf not in ("false", "input"):
            print(f"[FAIL] WSL: core.autocrlf='{autocrlf}', expected 'false' or 'input'")
            print("  Fix: git config core.autocrlf false")
            sys.exit(1)
        print(f"[OK] WSL: core.autocrlf='{autocrlf}'")
    else:
        # Other Linux / CI
        if autocrlf not in ("false", "input"):
            print(f"[FAIL] Linux: core.autocrlf='{autocrlf}', expected 'false' or 'input'")
            print("  Fix: git config core.autocrlf false")
            sys.exit(1)
        print(f"[OK] Linux: core.autocrlf='{autocrlf}'")


if __name__ == "__main__":
    main()