"""
test_ci_infrastructure.py — Testes de infraestrutura (NÃO-mock).

Validam que CI local/remoto vai passar SEM intervenção manual.
Esses testes rodam na fase unit do CI; problemas aqui são detectados
ANTES do push, antes de o Dependabot queue build.

Cobre:
  - requirements.txt parseable por pip-audit
  - pyproject.toml ignores/excludes corretos
  - ci.yml não referencia arquivos inexistentes
  - hooks têm shebang válido
  - sem dados operacionais trackeados
  - line endings consistentes (LF para .py/.md/.toml/.yml)
  - pip-audit não retorna vulnerabilidades
  - SECRET GUARD coverage (sk-, gsk_, etc.)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
REQUIREMENTS_TXT = REPO_ROOT / "requirements.txt"
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"
GITIGNORE = REPO_ROOT / ".gitignore"
GITATTRIBUTES = REPO_ROOT / ".gitattributes"
HOOKS_DIR = REPO_ROOT / ".githooks"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def pyproject_content() -> str:
    return PYPROJECT_TOML.read_text(encoding="utf-8")


def test_requirements_no_inline_flags() -> None:
    """requirements.txt não pode ter --index-url inline (quebra pip-audit)."""
    if not REQUIREMENTS_TXT.exists():
        pytest.skip("requirements.txt missing")
    content = REQUIREMENTS_TXT.read_text(encoding="utf-8")
    bad_pattern = re.compile(r"--(?:index|extra-index|trusted-host|find-links)-url")
    matches = [
        (i + 1, line.strip())
        for i, line in enumerate(content.splitlines())
        if bad_pattern.search(line)
    ]
    assert not matches, (
        "Inline pip flags detected (quebram pip-audit --strict):\n"
        + "\n".join(f"  linha {n}: {line}" for n, line in matches)
        + "\nUse PIP_INDEX_URL env var instead."
    )


def test_mypy_excludes_check_scripts(pyproject_content: str) -> None:
    """pyproject.toml deve excluir check_*.py da raiz do mypy."""
    assert '"check_*.py"' in pyproject_content, (
        'Adicione "check_*.py" ao mypy exclude em pyproject.toml '
        "(esses arquivos usam `supabase.create_client` que falha em CI)."
    )


def test_ruff_per_file_ignores_scripts(pyproject_content: str) -> None:
    """ruff per-file-ignores deve incluir E741 e W292 para scripts/."""
    section = re.search(
        r'"scripts/\*\.py"\s*=\s*\[(.*?)\]', pyproject_content, re.DOTALL
    )
    assert section, 'Faltando ruff per-file-ignores para "scripts/*.py"'
    rules = section.group(1)
    for code in ("E741", "W292"):
        assert code in rules, (
            f"Adicione {code} à lista de ignores em scripts/*.py "
            "(evita lint errors em diagnostics scripts)."
        )


def test_ci_yml_referenced_files_exist() -> None:
    """ci.yml não pode referenciar scripts Python inexistentes."""
    if not CI_YML.exists():
        pytest.skip("ci.yml missing")
    content = CI_YML.read_text(encoding="utf-8")
    referenced = set(re.findall(r"\b([\w/]+\.py)\b", content))
    missing = [f for f in referenced if not (REPO_ROOT / f).exists()]
    assert not missing, (
        f"ci.yml referencia arquivos inexistentes: {missing}"
    )


def test_githooks_have_valid_shebang() -> None:
    """Todos os githooks devem ter shebang válido (bash ou python)."""
    if not HOOKS_DIR.exists():
        pytest.skip("no .githooks directory")
    valid = (
        "#!/usr/bin/env bash",
        "#!/bin/bash",
        "#!/bash",
        "#!/usr/bin/env python",
        "#!/usr/bin/env python3",
        "#!/usr/bin/python",
        "#!/usr/bin/python3",
    )
    bad = []
    for hook in HOOKS_DIR.iterdir():
        if hook.is_file() and not hook.name.startswith("."):
            if hook.suffix in (".pyc", ".pyo"):
                continue
            try:
                content_text = hook.read_text(encoding="utf-8", errors="ignore")
                first_line = content_text.split("\n", 1)[0] if content_text else ""
            except OSError as e:
                pytest.fail(f"Não consegui ler hook {hook.name}: {e}")
            if not any(first_line.startswith(s) for s in valid):
                bad.append(f"  {hook.name}: '{first_line[:60]}'")
    assert not bad, (
        "Githooks com shebang inválido:\n" + "\n".join(bad)
    )


def test_no_operational_files_tracked() -> None:
    """Arquivos operacionais (data/trackers, caches) não devem estar trackeados."""
    operational = [
        "data/cleanup_track.json",
        "data/prices_latest.json",
        "data/llm_cache.db",
        "scripts/diagnose.py",
    ]
    import shutil
    git_bin = shutil.which("git")
    if not git_bin:
        pytest.skip("git not available in test env")
    result = subprocess.run(  # noqa: S603
        [git_bin, "ls-files", "--", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("git not available in test env")
    tracked = set(result.stdout.splitlines())
    leaks = [f for f in operational if f in tracked]
    assert not leaks, (
        f"Arquivos operacionais estão no repo (deveriam estar no .gitignore): {leaks}"
    )


def test_gitignore_covers_known_patterns() -> None:
    """.gitignore deve cobrir padrões críticos (secrets, caches, modelos)."""
    if not GITIGNORE.exists():
        pytest.fail(".gitignore não existe")
    content = GITIGNORE.read_text(encoding="utf-8")
    required_patterns = [
        ".env",
        "*.pem",
        "*.pkl",
        "data/llm_cache.db",
        "scripts/diagnose.py",
        "api_configuration.json",
        "cline_config.json",
        "backup_*.sql",
    ]
    missing = [p for p in required_patterns if p not in content]
    assert not missing, (
        f".gitignore não cobre: {missing}. "
        f"Se algum desses arquivos for commitado, vazará secrets/caches/modelos."
    )


def test_gitattributes_normalizes_text_files() -> None:
    """.gitattributes deve normalizar LF para arquivos de texto."""
    if not GITATTRIBUTES.exists():
        pytest.skip(".gitattributes missing (no CRLF protection)")
    content = GITATTRIBUTES.read_text(encoding="utf-8")
    required = [
        "*.py",
        "*.md",
        "*.toml",
        "*.yml",
        "*.json",
    ]
    missing = [p for p in required if p not in content]
    assert not missing, (
        f".gitattributes falta normalização LF para: {missing}. "
        "Sem isso, Windows commita CRLF e git detecta tudo modificado."
    )


def test_pip_audit_returns_no_vulnerabilities() -> None:
    """pip-audit --strict não pode retornar vulnerabilidades."""
    if not REQUIREMENTS_TXT.exists():
        pytest.skip("requirements.txt missing")
    result = subprocess.run(
        [sys.executable, "-m", "pip_audit", "--strict", "-s", "osv", "-r", "requirements.txt"],
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


def test_audit_secrets_script_exists() -> None:
    """scripts/audit_secrets.py deve existir (CI e hook dependem dele)."""
    script = REPO_ROOT / "scripts" / "audit_secrets.py"
    assert script.exists(), "scripts/audit_secrets.py não existe"


def test_audit_secrets_returns_clean() -> None:
    """Repo não pode ter segredos de alta confiança."""
    script = REPO_ROOT / "scripts" / "audit_secrets.py"
    if not script.exists():
        pytest.skip("audit_secrets.py missing")
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(script), "--strict"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"audit_secrets --strict falhou:\n{result.stdout[:2000]}\n"
        f"stderr: {result.stderr[:500]}"
    )


def test_ruff_lints_project() -> None:
    """ruff deve passar limpos em todo o projeto."""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"ruff encontrou erros:\n{result.stdout[:2000]}"
    )


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
    pytest.fail(
        "mypy falhou:\n" + "\n".join(lines[:10])
    )

