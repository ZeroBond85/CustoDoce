#!/usr/bin/env python3
"""Check core.autocrlf is correct for the current platform.

Windows: must be 'true'.
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


def main():
    autocrlf = _get_autocrlf()
    on_windows = sys.platform == "win32"
    on_wsl = on_windows is False and _is_wsl()

    if on_windows:
        if autocrlf != "true":
            print(f"[FAIL] Windows: core.autocrlf='{autocrlf}', expected 'true'")
            print("  Fix: git config core.autocrlf true")
            sys.exit(1)
        print(f"[OK] Windows: core.autocrlf='{autocrlf}'")
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
