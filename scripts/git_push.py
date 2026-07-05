#!/usr/bin/env python3
"""
git_push.py — Push + CI Watch + Auto-retry.

Executa git push, assiste o CI do GitHub Actions até completar,
e tenta auto-correção (ruff) antes de falhar para o humano.

O pre-push hook continua rodando NORMALMENTE antes do push.
Após o push bem-sucedido, este script monitora o CI.

Usage:
    python scripts/git_push.py [<git-push-args>...]

Git alias (recomendado):
    git config --local alias.pw '!python scripts/git_push.py'
    Uso: git pw [args]

Variáveis de ambiente:
    CI_MAX_RETRIES=1    Número máximo de auto-retry (0 desativa)
    CI_WATCH_TIMEOUT=600   Timeout em segundos (mata o watch)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAX_RETRIES = int(os.environ.get("CI_MAX_RETRIES", "1"))
TIMEOUT = int(os.environ.get("CI_WATCH_TIMEOUT", "600"))


# ── helpers ──────────────────────────────────────────────────────────────


def _run(cmd, capture=True, timeout=None):
    try:
        return subprocess.run(  # noqa: S607 — cmd is always a known tool (git/gh/python)
            cmd,
            capture_output=capture,
            text=capture,
            timeout=timeout,
            cwd=REPO_ROOT,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "")


def _get_branch() -> str:
    return _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def _get_run_id(branch: str, exclude: str | None = None, deadline_sec: int = 60) -> str | None:
    """Poll for a new (or freshly running) CI run on the branch."""
    deadline = time.time() + deadline_sec
    while time.time() < deadline:
        result = _run([
            "gh", "run", "list", "--branch", branch, "--limit", "5",
            "--json", "databaseId,conclusion,status,workflowName,headSha",
        ])
        if result.returncode == 0 and result.stdout.strip():
            try:
                for r in json.loads(result.stdout):
                    rid = str(r["databaseId"])
                    if exclude and rid == exclude:
                        continue
                    if r.get("status") in ("queued", "in_progress", ""):
                        return rid
            except (json.JSONDecodeError, KeyError, IndexError):
                pass
        time.sleep(2)
    return None


def _parse_error(log: str) -> tuple[str, str]:
    """Retorna (tipo_erro, assinatura). Assinatura vazia = sem hash."""
    if not log:
        return ("unknown", "")

    if re.search(r"S60[0-9]|Bandit", log):
        m = re.search(r">>\s*Issue:\s*\[(\w+:\d+):(\w+)\]", log)
        return ("bandit", f"bandit:{m.group(1)}:{m.group(2)}") if m else ("bandit", "")

    if re.search(r"ruff|RUF\d{3}", log):
        m = re.search(r"(\S+\.\w+:\d+:\d+):\s+(\w+)", log)
        return ("ruff", f"ruff:{m.group(1)}:{m.group(2)}") if m else ("ruff", "")

    if re.search(r"pip-audit|CVE-\d{4}-\d+", log):
        m = re.search(r"(CVE-\d{4}-\d+)", log)
        return ("pip-audit", m.group(1)) if m else ("pip-audit", "")

    if re.search(r"FAILED\s|AssertionError", log):
        m = re.search(r"FAILED\s+(\S+\.\w+::\w+)", log)
        return ("pytest", f"pytest:{m.group(1)}") if m else ("pytest", "")

    if re.search(r"(?i)timeout|runner.*(?:offline|disconnect|error)|cancelled", log):
        return ("timeout", "")

    return ("unknown", "")


def _watch_ci(run_id: str) -> tuple[int, str]:
    """Bloqueia até CI terminar. Retorna (exit_code, erro_log)."""
    print(f"⏳  Assistindo CI (run #{run_id})...", file=sys.stderr)
    try:
        watch = subprocess.run(
            ["gh", "run", "watch", run_id, "--exit-status"],  # noqa: S607
            capture_output=False,
            timeout=TIMEOUT,
            cwd=REPO_ROOT,
        )
        return (watch.returncode, "")
    except subprocess.TimeoutExpired:
        return (124, "timeout")


def _failed_log(run_id: str) -> str:
    result = _run(["gh", "run", "view", run_id, "--log-failed"], timeout=30)
    return (result.stdout or "") + (result.stderr or "")


def _auto_fix_ruff() -> bool:
    f = _run(["python", "-m", "ruff", "check", ".", "--fix"])
    return f.returncode == 0


def _amend_and_force_push() -> bool:
    _run(["git", "add", "-u"], capture=True)
    _run(["git", "commit", "--amend", "--no-edit"], capture=True)
    p = _run(["git", "push", "--force-with-lease"])
    return p.returncode == 0


# ── main ─────────────────────────────────────────────────────────────────


def main() -> int:
    push_args = sys.argv[1:]

    # ── 1. Push ──────────────────────────────────────────────────────────
    print("🚀  git push...", file=sys.stderr)
    push = _run(["git", "push"] + push_args)
    if push.returncode != 0:
        if push.stdout:
            print(push.stdout, end="")
        if push.stderr:
            print(push.stderr, end="", file=sys.stderr)
        return 1

    # ── 2. gh check ──────────────────────────────────────────────────────
    gh = _run(["gh", "auth", "status"], timeout=10)
    if gh.returncode != 0:
        print("⚠️   gh não autenticado. CI não será monitorado.", file=sys.stderr)
        print("    Rode: gh auth login", file=sys.stderr)
        return 0

    branch = _get_branch()
    print(f"🔍  Aguardando CI em {branch} ...", file=sys.stderr)

    run_id = _get_run_id(branch, deadline_sec=60)
    if not run_id:
        print("⚠️   Nenhum run do CI encontrado para este branch.", file=sys.stderr)
        return 0

    # ── 3. Watch + auto-retry loop ───────────────────────────────────────
    last_signature = ""
    last_run_id = run_id

    for attempt in range(MAX_RETRIES + 1):
        exit_code, _ = _watch_ci(last_run_id)

        if exit_code == 0:
            print("✅  CI passou com sucesso!", file=sys.stderr)
            return 0

        error_log = _failed_log(last_run_id)
        error_type, signature = _parse_error(error_log)

        # Diferente do erro anterior → stop
        if signature and last_signature and signature != last_signature:
            print(f"❌  Erro mudou: '{signature}' (era '{last_signature}')", file=sys.stderr)
            print("    Auto-fix pode ter introduzido regressão. Humano assume.", file=sys.stderr)
            break

        if attempt >= MAX_RETRIES:
            break

        last_signature = signature

        # ── Auto-fix ruff ────────────────────────────────────────────────
        if error_type == "ruff" and signature:
            print("🔄  Auto-fix ruff → re-push...", file=sys.stderr)
            if not _auto_fix_ruff():
                print("⚠️   ruff --fix falhou.", file=sys.stderr)
                break
            if not _amend_and_force_push():
                print("❌  Force-push falhou (branch atualizada?). Humano assume.", file=sys.stderr)
                break

            new_id = _get_run_id(branch, exclude=last_run_id, deadline_sec=60)
            if new_id:
                last_run_id = new_id
                continue
            print("⚠️   Novo run não detectado após auto-fix.", file=sys.stderr)
            break

        # ── Re-run flaky ─────────────────────────────────────────────────
        if error_type == "timeout":
            print("🔄  Re-executando workflow (flaky)...", file=sys.stderr)
            rerun = _run(["gh", "run", "rerun", last_run_id])
            if rerun.returncode != 0:
                print("❌  Re-run falhou.", file=sys.stderr)
                break
            time.sleep(5)
            continue

        # ── Outros erros ─────────────────────────────────────────────────
        print(f"❌  Erro não-fixável: {error_type} {signature}".strip(), file=sys.stderr)
        break

    # ── 4. Relatório de falha ────────────────────────────────────────────
    print("\n❌  CI FALHOU após todas as tentativas.", file=sys.stderr)
    log = _failed_log(last_run_id)
    if log:
        print("\n--- Log de erro (últimas 1500 chars) ---", file=sys.stderr)
        print(log[-1500:], file=sys.stderr)
        print("--- Fim do log ---", file=sys.stderr)

    print("\nSugestão:", file=sys.stderr)
    print("  1. python scripts/ci_local.py --lint --typecheck", file=sys.stderr)
    print("  2. Corrija localmente + git commit", file=sys.stderr)
    print("  3. python scripts/git_push.py", file=sys.stderr)
    print("  (use 'git push' para pular o CI watch)", file=sys.stderr)

    return 1


if __name__ == "__main__":
    sys.exit(main())
