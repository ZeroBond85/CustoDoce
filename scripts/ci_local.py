#!/usr/bin/env python3
"""
ci_local.py — Simula CI localmente antes do push.

Executa os mesmos jobs do .github/workflows/ci.yml:
  1. lint        (ruff, bandit, pip-audit)
  2. typecheck   (mypy)
  3. unit        (pytest)
  4. config-validate (local: requisitos que CI nao valida)

NOTA: docs-sync (sync_docs --check --strict + auto-fix) foi movido para o
pre-push hook (roda a versao rigorosa la). O ci_local NAO roda mais
docs-sync para evitar duplicacao. Devs: python scripts/sync_docs.py --check --strict

Uso:
  python scripts/ci_local.py           # todos os jobs
  python scripts/ci_local.py --lint    # só lint
  python scripts/ci_local.py --unit    # só pytest
  python scripts/ci_local.py --config  # só validação de config

Validações de config (só neste script):
  - requirements.txt: sem --index-url inline (quebra pip-audit)
  - pyproject.toml: mypy exclude cobre check_*.py na raiz
  - ci.yml: jobs não referencing arquivos inexistentes
  - Todos os arquivos em .github/workflows/*.yml existem
  - hooks válidos (sem syntax errors)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
REQUIREMENTS_TXT = REPO_ROOT / "requirements.txt"
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"
CI_WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
HOOKS_DIR = REPO_ROOT / ".githooks"
GITIGNORE = REPO_ROOT / ".gitignore"

# Carrega .env se existir (para ambiente local)
_dotenv = REPO_ROOT / ".env"
if _dotenv.exists():
    with open(_dotenv, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and "=" in _line and not _line.startswith("#"):
                _k, _v = _line.split("=", 1)
                _v = _v.strip("'\"").strip()
                os.environ.setdefault(_k.strip(), _v)

# Env vars esperadas pela CI — required vs optional
CI_ENV_REQUIRED = {
    "SUPABASE_URL": "URL do projeto Supabase (usado em integration/deploy-check)",
    "SUPABASE_SERVICE_ROLE_KEY": "Chave service_role (REST anon + RPC em integration tests)",
    "GROQ_API_KEY": "API key Groq (LLM classifier — necessária para testes de IA)",
}
CI_ENV_OPTIONAL = {
    "SUPABASE_ANON_KEY": "Chave anon (opcional — get_supabase() faz fallback para service_role)",
    "SUPABASE_DB_PASSWORD": "Senha direta do DB (porta 5432 — raramente usada em CI)",
    "TELEGRAM_TOKEN": "Token do bot Telegram (opcional — usado em e2e/real)",
    "TELEGRAM_CHAT_ID": "Chat ID do Telegram (opcional)",
    "GMAIL_USER": "Usuário Gmail SMTP (opcional — relatório diário)",
    "GMAIL_APP_PASSWORD": "Senha de app Gmail (opcional)",
    "ALERT_EMAIL_TO": "Destinatário de alertas (opcional)",
    "SMTP_HOST": "Host SMTP alternativo (opcional)",
    "SMTP_USER": "Usuário SMTP (opcional)",
    "SMTP_PASSWORD": "Senha SMTP (opcional)",
    "AUTH_SECRET_KEY": "Chave de autenticação do dashboard (opcional em CI)",
}


def run(cmd: str, cwd: Path = REPO_ROOT, capture: bool = True) -> subprocess.CompletedProcess:
    """Executa comando shell, usando o mesmo Python que roda este script."""
    py = sys.executable
    if cmd.startswith("python "):
        quoted_py = f'"{py}"' if " " in py else py
        actual_cmd = cmd.replace("python ", f"{quoted_py} ", 1)
    else:
        actual_cmd = cmd
    print(f"  $ {actual_cmd}")
    # timeout de seguranca: nenhuma verificacao local deve travar o hook
    # (pip-audit e rede tem timeout proprio; aqui cobre o subprocess em geral).
    result = subprocess.run(  # noqa: S602
        actual_cmd,
        shell=True,
        cwd=cwd,
        capture_output=capture,
        text=True,
        timeout=600,
    )
    return result


def job(name: str, ok: bool, details: str = "") -> bool:
    """Reporta resultado de um job."""
    status = "[OK]" if ok else "[FAIL]"
    print(f"{status} [{name}]")
    if details:
        print(textwrap.indent(details, "   "))
    return ok


# ─── Config Validations (antes de qualquer outra coisa) ────────────────────────


def validate_requirements_no_inline_flags() -> tuple[bool, str]:
    """requirements.txt não pode ter --index-url/--extra-index-url inline."""
    if not REQUIREMENTS_TXT.exists():
        return True, "requirements.txt não existe (pode ser projeto sem runtime deps)"
    content = REQUIREMENTS_TXT.read_text()
    lines_with_flags = [
        (i + 1, line)
        for i, line in enumerate(content.splitlines())
        if re.search(r"--(?:index|extra-index|trusted-host|find-links)-url", line)
    ]
    if lines_with_flags:
        details = "\n".join(f"  linha {n}: {line.strip()}" for n, line in lines_with_flags)
        return False, f"--index-url inline detectado:\n{details}\nUse PIP_INDEX_URL env var na CI."
    return True, ""


def validate_mypy_excludes_check_scripts() -> tuple[bool, str]:
    """pyproject.toml deve excluir check_*.py da raiz do mypy."""
    if not PYPROJECT_TOML.exists():
        return True, ""
    content = PYPROJECT_TOML.read_text()
    if re.search(r'"check_\*\.py"', content):
        return True, ""
    return False, 'Adicione "check_*.py" ao mypy exclude em pyproject.toml'


def validate_pyproject_ruff_per_file_ignores() -> tuple[bool, str]:
    """ruff per-file-ignores deve incluir E741 e W292 para scripts/."""
    if not PYPROJECT_TOML.exists():
        return True, ""
    content = PYPROJECT_TOML.read_text()
    scripts_ignores = re.search(r'"scripts/\*\.py"\s*=\s*\[(.*?)\]', content, re.DOTALL)
    if scripts_ignores:
        ignores = scripts_ignores.group(1)
        missing = []
        for code in ["E741", "W292"]:
            if code not in ignores:
                missing.append(code)
        if missing:
            return False, f"scripts/*.py ignora: faltam {missing} em pyproject.toml"
    return True, ""


def validate_ci_workflow_files_exist() -> tuple[bool, str]:
    """Todos os arquivos referenciados em ci.yml (scripts/, paths) devem existir."""
    ci_yml = CI_WORKFLOW_DIR / "ci.yml"
    if not ci_yml.exists():
        return False, "ci.yml não existe"
    content = ci_yml.read_text()
    referenced_files = re.findall(r"(?:run|python|script):\s*(?:python\s+)?(\S+\.py)", content)
    missing = []
    for f in referenced_files:
        fpath = REPO_ROOT / f
        if not fpath.exists():
            missing.append(f)
    if missing:
        return False, f"Arquivos em ci.yml não existem: {missing}"
    return True, ""


def validate_gitignore_has_diagnose() -> tuple[bool, str]:
    """scripts/diagnose.py deve estar no .gitignore."""
    if not GITIGNORE.exists():
        return False, ".gitignore não existe"
    content = GITIGNORE.read_text()
    if "scripts/diagnose.py" in content or "scripts/" in content:
        return True, ""
    # Scripts pessoais não devem ser trackeados
    diagnose = REPO_ROOT / "scripts" / "diagnose.py"
    if not diagnose.exists():
        return True, ""  # nem existe, ok
    return False, "scripts/diagnose.py existe mas não está no .gitignore"


def validate_no_untracked_json_in_data() -> tuple[bool, str]:
    """data/cleanup_track.json e similares (operacionais) não devem ser trackeados."""
    data_dir = REPO_ROOT / "data"
    if not data_dir.exists():
        return True, ""
    operational = ["cleanup_track.json", "prices_latest.json", "llm_cache.db"]
    tracked = []
    git_result = run("git ls-files data/", capture=True)
    if git_result.returncode == 0:
        tracked = git_result.stdout.splitlines()
    issues = []
    for f in operational:
        if f in tracked:
            issues.append(f"data/{f} está trackeado (deve ser .gitignore)")
    if issues:
        return False, "\n".join(f"  {i}" for i in issues)
    return True, ""


def validate_hooks_syntax() -> tuple[bool, str]:
    """Githooks: verifica shebang e básica integridade (funciona em qualquer OS)."""
    if not HOOKS_DIR.exists():
        return True, ""
    hooks = list(HOOKS_DIR.glob("*"))
    errors = []
    for hook in hooks:
        if hook.is_file() and not hook.name.startswith("."):
            content = hook.read_text(errors="ignore")
            if not content:
                errors.append(f"{hook.name}: arquivo vazio")
                continue
            first_line = content.splitlines()[0] if content else ""
            valid_shebangs = {
                "#!/usr/bin/env bash",
                "#!/bin/bash",
                "#!/bash",
                "#!/usr/bin/env python3",
                "#!/usr/bin/env python",
                "#!/usr/bin/python3",
                "#!/usr/bin/python",
            }
            if not any(first_line.startswith(s) for s in valid_shebangs):
                errors.append(f"{hook.name}: shebang inválido '{first_line}'")
    if errors:
        return False, "\n".join(errors)
    return True, ""


def validate_ci_env_vars() -> tuple[bool, str]:
    """Verifica se as env vars necessárias para CI estão configuradas localmente."""
    import os

    missing_required = []
    missing_optional = []
    for var, desc in CI_ENV_REQUIRED.items():
        if not os.environ.get(var):
            missing_required.append(f"  {var} — {desc}")
    for var, desc in CI_ENV_OPTIONAL.items():
        if not os.environ.get(var):
            missing_optional.append(f"  {var} — {desc}")
    parts = []
    if missing_required:
        parts.append("FALTAM (required — vão falhar no CI):\n" + "\n".join(missing_required))
    if missing_optional:
        parts.append("Ausentes (optional — warning):\n" + "\n".join(missing_optional[:5]))
        if len(missing_optional) > 5:
            parts[-1] += f"\n  ... e mais {len(missing_optional) - 5} opcionais"
    if parts:
        return len(missing_required) == 0, "\n\n".join(parts)
    return True, "Todas as env vars CI estão configuradas"


def run_config_validation() -> bool:
    """Executa todas as validações de configuração."""
    print("\n=== [config-validate] Validando config do projeto ===")
    checks = [
        ("requirements-no-inline-flags", validate_requirements_no_inline_flags),
        ("mypy-excludes-check-scripts", validate_mypy_excludes_check_scripts),
        ("ruff-per-file-ignores", validate_pyproject_ruff_per_file_ignores),
        ("ci-workflow-files-exist", validate_ci_workflow_files_exist),
        ("gitignore-diagnose", validate_gitignore_has_diagnose),
        ("no-operational-data-tracked", validate_no_untracked_json_in_data),
        ("hooks-syntax", validate_hooks_syntax),
        ("ci-env-vars", validate_ci_env_vars),
    ]
    all_ok = True
    for name, fn in checks:
        ok, details = fn()
        if not job(f"config/{name}", ok, details):
            all_ok = False
    return all_ok


# ─── CI Jobs ──────────────────────────────────────────────────────────────────


def run_lint() -> bool:
    """ruff + bandit + pip-audit."""
    print("\n=== [lint] ruff + bandit + pip-audit ===")
    all_ok = True

    result = run("python -m ruff check .")
    if not job("ruff", result.returncode == 0, result.stdout if result.returncode else ""):
        all_ok = False

    result = run("python -m bandit -r admin/ dashboard/ services/ -x tests/")
    if not job("bandit", result.returncode == 0, result.stdout if result.returncode else ""):
        all_ok = False

    # --timeout 30 blinda contra travamento de rede no PyPI/OSV (o pre-push
    # nao deve bloquear o push se o servidor de vulnerabilidades estiver lento).
    result = run("python -m pip_audit --strict --timeout 30 -s osv -r requirements.txt")
    if not job("pip-audit", result.returncode == 0, result.stdout if result.returncode else ""):
        all_ok = False

    return all_ok


def run_typecheck() -> bool:
    """mypy."""
    print("\n=== [typecheck] mypy ===")
    result = run("python -m mypy . --config-file pyproject.toml")
    ok = result.returncode == 0
    output = result.stdout + result.stderr if result.returncode else ""
    if "Success: no issues found" not in output and result.returncode != 0:
        job("mypy", False, output[:500])
    else:
        job("mypy", ok, "Success: no issues found")
    return ok


def run_unit() -> bool:
    """pytest unit + schema."""
    print("\n=== [unit] pytest tests/unit tests/schema ===")
    result = run("python -m pytest tests/unit/ tests/schema/ -q --tb=short --no-header")
    ok = result.returncode == 0
    output = (result.stdout + result.stderr)[-500:] if result.stdout else ""
    job("pytest", ok, output)
    return ok


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="CI local antes do push")
    parser.add_argument("--lint", action="store_true", help="Só lint")
    parser.add_argument("--typecheck", action="store_true", help="Só mypy")
    parser.add_argument("--unit", action="store_true", help="Só pytest")
    parser.add_argument("--no-unit", action="store_true", help="Pula pytest (para hooks)")
    parser.add_argument("--config", action="store_true", help="Só validação de config")
    parser.add_argument("--all", action="store_true", help="Todos os jobs")
    args = parser.parse_args()

    if not any([args.lint, args.typecheck, args.unit, args.config, args.all]):
        if args.no_unit:
            args.lint = True
            args.typecheck = True
            args.config = True
        else:
            args.all = True

    if args.all and args.no_unit:
        args.unit = False

    results = []

    if args.config or args.all:
        results.append(("config", run_config_validation()))

    if args.lint or args.all:
        results.append(("lint", run_lint()))

    if args.typecheck or args.all:
        results.append(("typecheck", run_typecheck()))

    if args.unit or args.all:
        results.append(("unit", run_unit()))

    # NOTA: docs-sync (sync_docs --check --strict + auto-fix) foi movido para o
    # pre-push hook, que roda a versao rigorosa. O ci_local NAO roda mais
    # docs-sync para evitar duplicacao ("2 docs sync"). Devs que quiserem
    # checar manualmente: python scripts/sync_docs.py --check --strict

    print("\n" + "=" * 60)
    print("RESUMO:")
    for name, ok in results:
        print(f"  {'[OK]' if ok else '[FAIL]'} {name}")
    print("=" * 60)

    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
