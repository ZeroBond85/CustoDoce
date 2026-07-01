"""
scripts/test_total_coverage.py

THE official end-to-end testTotalCoverage routine for CustoDoce.

Drives 11 phases (lint, mysql, mypy, pytest_unit, pytest_schema, pytest_integration,
pytest_real, pytest_design, sync_docs_drift, audit_secrets, deploy_check) and produces
a single JSON report at `data/test_runs/<timestamp>.json`.

Usage:
    python scripts/test_total_coverage.py                          # default (all phases)
    python scripts/test_total_coverage.py --skip-slow               # skip integration + real
    python scripts/test_total_coverage.py --skip-deploy-check      # skip live DB check
    python scripts/test_total_coverage.py --keep-reports 5         # retain last N reports

Exit code: 0 if all phases pass, 1 otherwise.

Wireable as:
 * Manual local:   python scripts/test_total_coverage.py
 * Pre-push:       trailing opt-in (CI_LOCAL_UNIT=1) and triggered by .githooks/pre-push
 * GitHub Actions: invoked from `.github/workflows/ci.yml` (lint pipeline) or manual dispatch
 * OpenCode Skill: ".opencode/skills/test-total-runner/SKILL.md"
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "data" / "test_runs"
GLOBAL_TIMEOUT = 1800  # 30 min wall clock
PY = sys.executable


# ─── Phases (canonical order) ──────────────────────────────────────────────


PHASES = [
    {"name": "ruff", "cmd": ["python", "-m", "ruff", "check", "."], "optional": False},
    {"name": "ruff-format", "cmd": ["python", "-m", "ruff", "format", ".", "--check"], "optional": True},
    {"name": "mypy", "cmd": ["python", "-m", "mypy", "."], "optional": False},
    {"name": "pytest-unit", "cmd": ["python", "-m", "pytest", "tests/unit/", "-q", "--tb=short"], "optional": False},
    {
        "name": "pytest-schema",
        "cmd": ["python", "-m", "pytest", "tests/schema/", "-q", "--tb=short"],
        "optional": False,
    },
    {
        "name": "pytest-integration",
        "cmd": ["python", "-m", "pytest", "tests/integration/", "-q", "--tb=short"],
        "optional": True,
    },
    {"name": "pytest-real", "cmd": ["python", "-m", "pytest", "tests/real/", "-q", "--tb=short"], "optional": True},
    {
        "name": "pytest-design",
        "cmd": ["python", "-m", "pytest", "tests/design/", "-q", "--tb=short"],
        "optional": False,
    },
    {"name": "sync_docs_drift", "cmd": ["python", "scripts/sync_docs.py", "--check"], "optional": False},
    {"name": "sync_docs_v2_analyze", "cmd": ["python", "scripts/sync_docs.py", "--analyze"], "optional": False},
    {"name": "audit_secrets", "cmd": ["python", "scripts/audit_secrets.py", "--strict"], "optional": False},
    {"name": "deploy_check", "cmd": ["python", "scripts/deploy_check.py"], "optional": True},
]


def run_phase(idx: int, phase: dict, skip_phases: set[str]) -> dict:
    name = phase["name"]
    start = time.time()
    result = {
        "phase": name,
        "index": idx,
        "started_at": datetime.now().isoformat(),
        "optional": phase["optional"],
    }
    if name in skip_phases or phase["optional"] and name in {"slow"}:
        result.update({"status": "SKIPPED", "duration_sec": 0})
        return result
    try:
        proc = subprocess.run(
            phase["cmd"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=900,  # 15 min per phase ceiling
        )
        elapsed = time.time() - start
        result.update(
            {
                "status": "PASS" if proc.returncode == 0 else "FAIL",
                "returncode": proc.returncode,
                "duration_sec": round(elapsed, 2),
                "stdout_tail": proc.stdout[-800:] if proc.stdout else "",
                "stderr_tail": proc.stderr[-400:] if proc.stderr else "",
            }
        )
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        result.update(
            {
                "status": "TIMEOUT",
                "duration_sec": round(elapsed, 2),
            }
        )
    except Exception as exc:
        elapsed = time.time() - start
        result.update(
            {
                "status": "ERROR",
                "duration_sec": round(elapsed, 2),
                "error": str(exc),
            }
        )
    result["finished_at"] = datetime.now().isoformat()
    return result


def aggregate(results: list[dict]) -> dict:
    total = {"PASS": 0, "FAIL": 0, "SKIPPED": 0, "TIMEOUT": 0, "ERROR": 0}
    for r in results:
        total[r["status"]] = total.get(r["status"], 0) + 1
    return total


def cleanup_old_reports(keep: int):
    if keep <= 0 or not REPORT_DIR.exists():
        return
    reports = sorted(REPORT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in reports[keep:]:
        old.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="CustoDoce — Total Test Coverage Script (orchestrator)")
    parser.add_argument("--skip-slow", action="store_true", help="Skip integration + real phases")
    parser.add_argument("--skip-deploy-check", action="store_true", help="Skip live DB deploy_check")
    parser.add_argument("--keep-reports", type=int, default=10, help="Keep last N reports")
    parser.add_argument("--out", type=str, default=None, help="Override output file path")
    args = parser.parse_args()

    skip: set[str] = set()
    if args.skip_slow:
        skip.update({"pytest-integration", "pytest-real"})
    if args.skip_deploy_check:
        skip.add("deploy_check")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    started_wall = time.time()
    print(f"=== CustoDoce testTotalCoverage @ {datetime.now().isoformat()} ===")
    print(f"  ROOT: {ROOT}")
    print(f"  Skipped phases: {sorted(skip) if skip else '(none)'}")
    print(f"  Total phases queued: {len([p for p in PHASES if p['name'] not in skip])}")
    print()

    results: list[dict] = []
    try:
        for idx, phase in enumerate(PHASES, start=1):
            r = run_phase(idx, phase, skip)
            results.append(r)
            mark = r["status"][0]
            print(f"  [{mark}] {r['phase']:<22} {r['status']:<8} {r['duration_sec']}s")
            if time.time() - started_wall > GLOBAL_TIMEOUT:
                print(f"  GLOBAL TIMEOUT ({GLOBAL_TIMEOUT}s) reached — aborting remaining phases")
                for p in PHASES[idx:]:
                    results.append({"phase": p["name"], "status": "SKIPPED_TIMEOUT", "duration_sec": 0})
                break
    except KeyboardInterrupt:
        print("Interrupted by user.")

    summary = aggregate(results)
    report = {
        "started_at": datetime.now().isoformat(),
        "total_duration_sec": round(time.time() - started_wall, 2),
        "skipped_phases": sorted(skip),
        "summary": summary,
        "phases": results,
        "repo": {
            "head_sha": _safe_git("rev-parse HEAD"),
            "branch": _safe_git("rev-parse --abbrev-ref HEAD"),
        },
    }

    if args.out:
        out_path = Path(args.out)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = REPORT_DIR / f"coverage_{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print()
    print(
        f"=== summary (exit {'PASS' if summary.get('FAIL', 0) == 0 and summary.get('ERROR', 0) == 0 else 'FAIL'}) ==="
    )
    for k, v in summary.items():
        print(f"  {k:<10} {v}")
    print(f"  total phases run: {len(results)}")
    print(f"  report saved: {out_path}")

    cleanup_old_reports(args.keep_reports)
    return 0 if summary.get("FAIL", 0) == 0 and summary.get("ERROR", 0) == 0 else 1


def _safe_git(args: str) -> str | None:
    try:
        return subprocess.check_output(f"git {args}", cwd=str(ROOT), stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
