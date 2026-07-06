# mypy: ignore-errors
#!/usr/bin/env python
"""
check_environment_parity.py

Paridade Total de Ambiente — valida que Python + deps + OS correspondem
aos requisitos do projeto, e que requirements.lock está íntegro.

- Em CI (GITHUB_ACTIONS): falha HARD se Python != 3.14.
- Local: avisa (warn) se Python != 3.14, mas não bloqueia.
- requirements.lock dry-run: sempre HARD failure se pip resolve falhar.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
REQUIRED_PYTHON = (3, 14)
LOCK_FILE = REPO_ROOT / "requirements.lock"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
IN_CI = os.environ.get("GITHUB_ACTIONS") == "true"


def _check_python_version() -> list[str]:
    errors: list[str] = []
    warnings: list[str] = []
    actual = sys.version_info[:2]
    if actual != REQUIRED_PYTHON:
        msg = f"Python {actual[0]}.{actual[1]} detectado, mas {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]} exigido."
        if IN_CI:
            errors.append(msg)
        else:
            warnings.append(f"[WARN] {msg} (ignorado localmente — CI vai validar)")
    return errors, warnings


def _check_platform() -> list[str]:
    errors: list[str] = []
    system = platform.system()
    if system not in ("Windows", "Linux"):
        errors.append(f"Plataforma nao suportada: {system}")
    return errors


def _check_lock_valid() -> list[str]:
    errors: list[str] = []
    if not LOCK_FILE.exists():
        errors.append(f"requirements.lock nao encontrado em {LOCK_FILE}")
        return errors

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--dry-run", "-r", str(LOCK_FILE)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )
    if result.returncode != 0:
        errors.append(f"pip dry-run falhou: {result.stderr.strip()[-500:]}")
    return errors


def _check_agents_md_rule_10() -> list[str]:
    errors: list[str] = []
    if not AGENTS_MD.exists():
        errors.append("AGENTS.md nao encontrado — não foi possível verificar rule #10.")
        return errors

    content = AGENTS_MD.read_text(encoding="utf-8")
    if "Paridade Total de Ambiente" not in content:
        errors.append(
            "AGENTS.md rule #10 nao menciona 'Paridade Total de Ambiente'. "
            "Reinstale a regra Top-10 com scripts/agents_tool.py --add-rule."
        )
    return errors


def main() -> int:
    print(
        f"=== check_environment_parity (CI={IN_CI}, platform={platform.system()}, python={sys.version})",
        file=sys.stderr,
    )

    all_errors: list[str] = []
    all_warnings: list[str] = []

    py_errors, py_warnings = _check_python_version()
    all_errors.extend(py_errors)
    all_warnings.extend(py_warnings)

    all_errors.extend(_check_platform())
    all_errors.extend(_check_lock_valid())
    all_errors.extend(_check_agents_md_rule_10())

    for w in all_warnings:
        print(w, file=sys.stderr)
    if not all_errors:
        print("[OK] Todas as verificacoes de paridade passaram.", file=sys.stderr)
        return 0
    for err in all_errors:
        print(f"[FALHA] {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
