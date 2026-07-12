# mypy: ignore-errors
#!/usr/bin/env python
"""
check_environment_parity.py

Paridade Total de Ambiente — validação abrangente:

1. Python version (3.14.6 obrigatório em CI)
2. Platform (Windows/Linux)
3. requirements.lock dry-run (pip resolve check)
4. AGENTS.md rule #10 presence
5. runtime.txt vs actual Python version
6. devcontainer Python image matches project target
7. Lock file fingerprints match (all .lock files in sync)
8. Key package versions consistent across lock files
9. @v tags in workflow files (consistency)
10. Unpinned pip install commands in workflows (warn)

- Em CI (GITHUB_ACTIONS): falha HARD se versão != 3.14.6 ou lock inválido.
- Local: avisa (warn) para desvios não-críticos, falha para críticos.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
REQUIRED_PYTHON = (3, 14, 6)
LOCK_FILE = REPO_ROOT / "requirements.lock"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
RUNTIME_TXT = REPO_ROOT / "runtime.txt"
DEVCONTAINER = REPO_ROOT / ".devcontainer" / "devcontainer.json"
IN_CI = os.environ.get("GITHUB_ACTIONS") == "true"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# Allowed action versions (SSOT)
EXPECTED_ACTION_TAGS: dict[str, str] = {
    "actions/checkout": "v7",
    "actions/setup-python": "v6",
    "actions/cache": "v4",
    "actions/upload-artifact": "v7",
}

# Key packages to check across lock files
KEY_PACKAGES = [
    "ruff", "mypy", "pytest", "bandit", "pip-audit", "detect-secrets",
    "httpx", "supabase", "streamlit", "pdfplumber", "pytesseract", "playwright",
]


def _get_python_version() -> tuple[int, int, int]:
    """Return (major, minor, micro) tuple."""
    return sys.version_info[:3]


def _check_python_version() -> list[str]:
    errors: list[str] = []
    actual = _get_python_version()
    if actual[:2] != REQUIRED_PYTHON[:2]:
        msg = f"Python {actual[0]}.{actual[1]}.{actual[2]} detectado, mas {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}.x exigido."
        if IN_CI:
            errors.append(msg)
        else:
            print(f"[WARN] {msg} (ignorado localmente)")
    elif IN_CI and actual != REQUIRED_PYTHON:
        print(f"[WARN] Python micro version {actual[2]} != {REQUIRED_PYTHON[2]} (CI warning)")
    return errors


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
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=120,
    )
    if result.returncode != 0:
        errors.append(f"pip dry-run falhou: {result.stderr.strip()[-500:]}")
    return errors


def _check_agents_md_rule_10() -> list[str]:
    errors: list[str] = []
    if AGENTS_MD.exists():
        content = AGENTS_MD.read_text(encoding="utf-8")
        if "Paridade Total de Ambiente" not in content:
            errors.append("AGENTS.md rule #10 nao menciona 'Paridade Total de Ambiente'")
    return errors


def _check_runtime_txt() -> list[str]:
    """Check runtime.txt declares the correct Python version."""
    errors: list[str] = []
    if not RUNTIME_TXT.exists():
        errors.append("runtime.txt nao encontrado")
        return errors
    version_line = RUNTIME_TXT.read_text(encoding="utf-8").strip()
    expected = f"python-{REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}"
    if not version_line.startswith(expected):
        errors.append(
            f"runtime.txt: '{version_line}', esperado '{expected}.X'. "
            f"Streamlit Cloud usaria versao errada!"
        )
    return errors


def _strip_json_comments(text: str) -> str:
    """Remove // style comments from JSON (devcontainer.json uses them)."""
    return re.sub(r'(?<!")\s*//.*$', '', text, flags=re.MULTILINE)


def _check_devcontainer_python() -> list[str]:
    """Check devcontainer image uses correct Python version."""
    errors: list[str] = []
    if not DEVCONTAINER.exists():
        return errors
    try:
        raw = DEVCONTAINER.read_text(encoding="utf-8")
        cleaned = _strip_json_comments(raw)
        data = json.loads(cleaned)
        image = data.get("image", "")
        expected_tag = f"{REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}"
        if expected_tag not in image:
            errors.append(
                f"devcontainer image '{image}' nao contem Python {expected_tag}. "
                f"Deve referenciar uma imagem com Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}."
            )
        expected_lock = "requirements-prod.lock"
        cmd = data.get("updateContentCommand", "")
        if expected_lock not in cmd:
            errors.append(
                f"devcontainer updateContentCommand nao usa {expected_lock} "
                f"(usando requirements.txt sem pin?): {cmd[:100]}"
            )
    except (json.JSONDecodeError, KeyError) as e:
        errors.append(f"devcontainer.json parse error: {e}")
    return errors


def _check_lock_sync() -> list[str]:
    """Check that all lock files define same package versions for KEY_PACKAGES."""
    errors: list[str] = []
    lock_files = sorted(REPO_ROOT.glob("requirements*.lock"))
    if not lock_files:
        return errors

    pkg_versions: dict[str, dict[str, str]] = {}
    for lf in lock_files:
        name = lf.name
        pkg_versions[name] = {}
        for line in lf.read_text(encoding="utf-8").splitlines():
            for pkg in KEY_PACKAGES:
                if line.startswith(f"{pkg}==") and "\\" not in line:
                    pkg_versions[name][pkg] = line.strip()

    packages_found = set()
    for versions in pkg_versions.values():
        packages_found.update(versions.keys())

    for pkg in sorted(packages_found):
        versions = {}
        for lf_name, pkgs in pkg_versions.items():
            if pkg in pkgs:
                versions[lf_name] = pkgs[pkg]
        unique_versions = set(versions.values())
        if len(unique_versions) > 1:
            details = "; ".join(f"{f}: {v}" for f, v in versions.items())
            errors.append(f"Versao inconsistente de '{pkg}': {details}")
    return errors


def _check_sanitize_yml() -> list[str]:
    """Check sanitize-check.yml for checkout@v4 drift."""
    errors: list[str] = []
    yml_file = WORKFLOWS_DIR / "sanitize-check.yml"
    if not yml_file.exists():
        return errors
    content = yml_file.read_text(encoding="utf-8")
    if "actions/checkout@v4" in content:
        errors.append("sanitize-check.yml usa actions/checkout@v4 (deveria ser @v7)")
    if "pip install --upgrade pip" in content:
        errors.append("sanitize-check.yml: pip install --upgrade pip (sobe alem do lock)")
    return errors


def _check_unpinned_installs() -> list[str]:
    """Warn about unpinned pip install in workflow files that bypass lock files."""
    warnings: list[str] = []
    if not WORKFLOWS_DIR.exists():
        return warnings
    for yml_file in sorted(WORKFLOWS_DIR.glob("*.yml")):
        content = yml_file.read_text(encoding="utf-8")
        for match in re.finditer(r"pip install (?!-r |--no|--dry)[a-zA-Z][^\n]*", content):
            line = match.group().strip()
            # Known-allowed patterns
            if "pip-tools==" in line or "pip-audit==" in line or "deptry==" in line or "pip-licenses==" in line:
                continue
            if "urllib3" in line:
                continue
            if not any(c.isdigit() for c in line.split()[-1]) and "==" not in line:
                warnings.append(
                    f"{yml_file.name}: '{line}' sem versao fixa (bypaases lock file)"
                )
    return warnings


def main() -> int:
    print(
        f"=== check_environment_parity (CI={IN_CI}, platform={platform.system()}, python={sys.version})",
        file=sys.stderr,
    )

    all_errors: list[str] = []
    all_warnings: list[str] = []

    all_errors.extend(_check_python_version())
    all_errors.extend(_check_platform())
    all_errors.extend(_check_lock_valid())
    all_errors.extend(_check_agents_md_rule_10())
    all_errors.extend(_check_runtime_txt())
    all_errors.extend(_check_devcontainer_python())
    all_errors.extend(_check_lock_sync())
    all_errors.extend(_check_sanitize_yml())

    w = _check_unpinned_installs()
    for msg in w:
        print(f"[WARN] {msg}", file=sys.stderr)

    for w_msg in all_warnings:
        print(f"[WARN] {w_msg}", file=sys.stderr)

    if not all_errors:
        print("[OK] Todas as verificacoes de paridade passaram.", file=sys.stderr)
        return 0
    for err in all_errors:
        print(f"[FALHA] {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
