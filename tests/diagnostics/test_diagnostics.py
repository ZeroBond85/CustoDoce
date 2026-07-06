"""Slow diagnostic tests: full-project lint/type/audit scans."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.slow
def test_pip_audit_returns_no_vulnerabilities() -> None:
    """pip-audit --strict não pode retornar vulnerabilidades."""
    req = REPO_ROOT / "requirements.txt"
    if not req.exists():
        return
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pip_audit", "--strict", "-s", "osv", "-r", str(req)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    out = (result.stdout or "") + (result.stderr or "")
    if "No known vulnerabilities found" in out:
        return
    pytest.fail(
        f"pip-audit encontrou vulns:\n{out[:2000]}\n\n"
        f"Atualize deps ou adicione GHSA ao --ignore-vulnerability de ci.yml."
    )


@pytest.mark.slow
def test_ruff_lints_project() -> None:
    """ruff deve passar limpos em todo o projeto."""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"ruff encontrou erros:\n{result.stdout[:2000]}"


@pytest.mark.slow
def test_mypy_passes() -> None:
    """mypy deve passar sem erros (apenas notes permitted)."""
    result = subprocess.run(
        [sys.executable, "-m", "mypy", ".", "--config-file", "pyproject.toml"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    out = (result.stdout or "") + (result.stderr or "")
    if result.returncode == 0:
        return
    lines = [line for line in out.splitlines() if line.startswith("Found") or "error:" in line]
    pytest.fail("mypy falhou:\n" + "\n".join(lines[:10]))


@pytest.mark.slow
def test_audit_secrets_returns_clean() -> None:
    """Repo não pode ter segredos de alta confiança."""
    script = REPO_ROOT / "scripts" / "audit_secrets.py"
    if not script.exists():
        return
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(script), "--strict"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"audit_secrets --strict falhou:\n{result.stdout[:2000]}\nstderr: {result.stderr[:500]}"
    )
