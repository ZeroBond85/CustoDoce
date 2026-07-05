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


def _get_run_ids(branch: str, exclude: set[str] | None = None, deadline_sec: int = 60) -> list[str]:
    """Poll for ALL CI runs on the branch. Returns list of run IDs."""
    deadline = time.time() + deadline_sec
    seen: set[str] = set(exclude) if exclude else set()
    while time.time() < deadline:
        result = _run([
            "gh", "run", "list", "--branch", branch, "--limit", "10",
            "--json", "databaseId,conclusion,status,workflowName,headSha",
        ])
        if result.returncode == 0 and result.stdout.strip():
            try:
                found = []
                for r in json.loads(result.stdout):
                    rid = str(r["databaseId"])
                    if rid in seen:
                        continue
                    if r.get("status") in ("queued", "in_progress", ""):
                        found.append(rid)
                        seen.add(rid)
                if found:
                    return found
            except (json.JSONDecodeError, KeyError, IndexError):
                pass
        time.sleep(2)
    return []


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


def _watch_one(run_id: str) -> tuple[int, str]:
    """Bloqueia até um run específico terminar. Retorna (exit_code, erro_log)."""
    wf = _get_workflow_name(run_id) or "?"
    print(f"⏳  Assistindo {wf} (run #{run_id})...", file=sys.stderr)
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


def _get_workflow_name(run_id: str) -> str:
    result = _run(["gh", "run", "view", run_id, "--json", "workflowName"])
    if result.returncode == 0 and result.stdout.strip():
        try:
            d = json.loads(result.stdout)
            return d.get("workflowName", "?")
        except json.JSONDecodeError:
            pass
    return "?"


def _watch_all(run_ids: list[str]) -> dict[str, tuple[int, str]]:
    """Watch ALL runs. Returns dict of {run_id: (exit_code, error_log)}."""
    results: dict[str, tuple[int, str]] = {}
    for rid in run_ids:
        code, _ = _watch_one(rid)
        elog = _failed_log(rid) if code != 0 else ""
        results[rid] = (code, elog)
    return results


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

    all_run_ids = _get_run_ids(branch, deadline_sec=60)
    if not all_run_ids:
        print("⚠️   Nenhum run do CI encontrado para este branch.", file=sys.stderr)
        return 0

    print(f"📊  Trabalhos detectados: {len(all_run_ids)}", file=sys.stderr)

    # ── 3. Watch ALL + auto-retry loop ───────────────────────────────────
    seen: set[str] = set()
    failed_run_ids: list[str] = []

    for attempt in range(MAX_RETRIES + 1):
        # Collect all runs (including new ones from re-runs)
        run_ids = _get_run_ids(branch, exclude=seen, deadline_sec=15)
        if not run_ids and not failed_run_ids:
            # No new runs and no previous failures → all good
            break

        all_ids = list(seen) + run_ids
        seen.update(run_ids)

        if not all_ids:
            break

        # Watch ALL runs
        results = _watch_all(all_ids)

        # Separate passed and failed
        failed = [rid for rid, (code, _) in results.items() if code != 0]
        any_timeout = False
        any_ruff = False
        ruff_rids: list[str] = []

        for rid in failed:
            elog = results[rid][1]
            etype, sig = _parse_error(elog)
            if etype == "ruff" and sig:
                any_ruff = True
                ruff_rids.append(rid)
            if etype == "timeout":
                any_timeout = True

        if not failed:
            print("✅  CI passou com sucesso!", file=sys.stderr)
            return 0

        if attempt >= MAX_RETRIES:
            failed_run_ids = failed
            break

        # ── Auto-fix ruff ───────────────────────────────────────────────
        if any_ruff:
            print("🔄  Auto-fix ruff → re-push...", file=sys.stderr)
            if not _auto_fix_ruff():
                print("⚠️   ruff --fix falhou.", file=sys.stderr)
                failed_run_ids = failed
                break
            if not _amend_and_force_push():
                print("❌  Force-push falhou. Humano assume.", file=sys.stderr)
                failed_run_ids = failed
                break
            # Don't clear seen — force-push creates new run IDs
            continue

        # ── Re-run flaky ─────────────────────────────────────────────────
        if any_timeout:
            print("🔄  Re-executando workflow(s) (flaky)...", file=sys.stderr)
            for rid in failed:
                if _parse_error(results[rid][1])[0] == "timeout":
                    _run(["gh", "run", "rerun", rid], timeout=15)
                    time.sleep(3)
            continue

        # ── Outros erros ─────────────────────────────────────────────────
        failed_run_ids = failed
        break

    # ── 4. Relatório de falha ────────────────────────────────────────────
    print("\n❌  CI FALHOU após todas as tentativas.", file=sys.stderr)
    for rid in failed_run_ids:
        wf = _get_workflow_name(rid)
        log = _failed_log(rid)
        print(f"\n--- {wf} (run #{rid}) ---", file=sys.stderr)
        if log:
            print(log[-1000:], file=sys.stderr)

    print("\nSugestão:", file=sys.stderr)
    print("  1. python scripts/ci_local.py --lint --typecheck", file=sys.stderr)
    print("  2. Corrija localmente + git commit", file=sys.stderr)
    print("  3. python scripts/git_push.py", file=sys.stderr)
    print("  (use 'git push' para pular o CI watch)", file=sys.stderr)

    return 1 if failed_run_ids else 0


if __name__ == "__main__":
    sys.exit(main())
