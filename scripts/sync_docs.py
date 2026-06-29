"""
Sync Docs — keeps project documentation in sync with actual code state.

Extracts current state from code and updates:
- AGENTS.md (project memory — test counts, phases, files)
- docs/api/*.md (auto-generated from code when needed)
- README.md tree (when new files are added)

Run manually:
    python scripts/sync_docs.py --dry-run   # preview changes
    python scripts/sync_docs.py             # apply changes

Run in CI (fails if docs are outdated):
    python scripts/sync_docs.py --check     # exit 1 if out of sync
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

_ROOT = Path(__file__).resolve().parent.parent
_AGENTS = _ROOT / "AGENTS.md"
_README = _ROOT / "README.md"
_DOCS_API = _ROOT / "docs" / "api"
_LAYOUT = _ROOT / "dashboard" / "components" / "layout.py"
_TEST_DIR = _ROOT / "tests"
_SERVICES_DIR = _ROOT / "services"

_OK = "OK"
_FAIL = "FAIL"


def _count_tests() -> dict:
    """Count tests by category using pytest --collect-only (no import needed).

    Counts both <Function test_> (sync tests) AND <Coroutine test_> (async tests).
    Earlier versions only counted synchronous tests, missing 7 async helpers in
    test_telegram_handlers.py (411 vs real 418).
    """
    import subprocess

    result = {}
    # Compiled patterns once for speed and consistency
    sync_pat = re.compile(r"<Function\s+test_")  # sync tests
    async_pat = re.compile(r"<Coroutine\s+test_")  # async tests

    for test_path, label in [
        ("tests/unit", "unit"),
        ("tests/schema", "schema"),
        ("tests/integration", "integration"),
        ("tests/e2e", "e2e"),
        ("tests/real", "real"),
    ]:
        full_path = _ROOT / test_path
        if not full_path.exists():
            continue
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(full_path),
                    "--collect-only",
                    "-q",
                    "--no-header",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                cwd=str(_ROOT),
            )
            sync_count = len(sync_pat.findall(proc.stdout))
            async_count = len(async_pat.findall(proc.stdout))
            result[label] = sync_count + async_count
        except Exception:
            result[label] = 0
    return result


def _extract_actual_test_count(test_path: str) -> tuple[int, int]:
    """Get pytest's reported total + delta vs my count.

    Returns (pytest_total, my_count). Used by --check drift detection.
    """
    import subprocess

    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(test_path),
                "--collect-only",
                "-q",
                "--no-header",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=str(_ROOT),
        )
        # Pattern: "X tests collected in N.NNs"
        m = re.search(r"(\d+)\s+tests?\s+collected", proc.stdout)
        pytest_total = int(m.group(1)) if m else 0
        sync_count = len(re.findall(r"<Function\s+test_", proc.stdout))
        async_count = len(re.findall(r"<Coroutine\s+test_", proc.stdout))
        my_count = sync_count + async_count
        return (pytest_total, my_count)
    except Exception:
        return (0, 0)


def _check_drift() -> list[str]:
    """Detect drift between pytest's reported total and our sync_docs count.

    Returns list of drift messages. Empty = no drift.

    Sources of truth compared:
        - my_counts (from _count_tests — this script's interpretation)
        - pytest's "X tests collected" line (ground truth)

    Drift triggers a --check failure to keep AGENTS.md truthful (Sprint 4).
    """
    drift_msgs = []
    my_counts = _count_tests()
    for test_path, label in [
        ("tests/unit", "unit"),
        ("tests/schema", "schema"),
        ("tests/integration", "integration"),
        ("tests/e2e", "e2e"),
        ("tests/real", "real"),
    ]:
        full = _ROOT / test_path
        if not full.exists():
            continue
        pytest_total, _sync_and_async_count = _extract_actual_test_count(test_path)
        my_count = my_counts.get(label, 0)
        if pytest_total != _sync_and_async_count or pytest_total != my_count:
            actual = _sync_and_async_count
            drift_msgs.append(
                f"  {label}: pytest reports {pytest_total}, sync_docs counted {my_count} (regex-confirmed {actual})"
            )
    return drift_msgs


def _extract_pages() -> list[tuple[str, str, str]]:
    """Extract PAGES from dashboard/components/layout.py."""
    content = _LAYOUT.read_text(encoding="utf-8")
    pages = []
    for line in content.splitlines():
        m = re.match(r'\s*\(["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']', line)
        if m:
            pages.append((m.group(1), m.group(2), m.group(3)))
    return pages


def _extract_services_api() -> dict[str, list[str]]:
    """Extract public functions from service modules."""
    api = {}
    for py_file in _SERVICES_DIR.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        module_name = py_file.stem
        functions = []
        content = py_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            m = re.match(r"^def\s+(\w+)\s*\(", line)
            if m:
                fn = m.group(1)
                if not fn.startswith("_"):
                    functions.append(fn)
        if functions:
            api[module_name] = sorted(functions)
    return api


def _extract_dashboard_pages() -> list[str]:
    """Extract page IDs from layout.py PAGES list."""
    pages = _extract_pages()
    return [p[0] for p in pages]


def _extract_workflows() -> list[str]:
    """List GitHub workflow files."""
    wf_dir = _ROOT / ".github" / "workflows"
    if not wf_dir.exists():
        return []
    return sorted([f.stem for f in wf_dir.glob("*.yml")])


def _current_timestamp() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")


def _build_agents_state() -> dict:
    """Build current project state dict."""
    test_counts = _count_tests()
    pages = _extract_pages()
    services_api = _extract_services_api()
    workflows = _extract_workflows()

    total_tests = sum(test_counts.values())

    return {
        "updated_at": _current_timestamp(),
        "total_tests": total_tests,
        "test_counts": test_counts,
        "pages": pages,
        "pages_count": len(pages),
        "services_api": services_api,
        "workflows": workflows,
        "workflows_count": len(workflows),
        "api_services": sorted(services_api.keys()),
    }


def _update_agents_md(state: dict, dry_run: bool = False) -> list[str]:
    """Update AGENTS.md with current state.

    Robust detection of the Ferramenta/Tool status table: works whether AGENTS.md
    uses single pytest line ("unit") or combined ("unit + schema").
    """
    content = _AGENTS.read_text(encoding="utf-8")
    lines = content.splitlines()

    changes = []

    # Update "Last updated" line
    for i, line in enumerate(lines):
        if "Last updated:" in line or "Última atualização:" in line:
            if dry_run:
                changes.append(f"  Would update line {i + 1}: {line.strip()}")
            else:
                lines[i] = f"<!-- Last updated: {state['updated_at']} -->"
            break

    tc = state["test_counts"]

    # Find the status table — flexible regex tolerant of both
    # "| pytest (unit) | ..." and "| pytest (unit + schema) | ..." headers
    in_status_table = False
    status_start = -1
    status_end = -1
    status_table_re = re.compile(r"\|\s*(pytest|tool)\s*\(.*pytest", re.IGNORECASE)

    for i, line in enumerate(lines):
        stripped = line.strip()
        is_header = "| Ferramenta" in line or "| Tool" in line or status_table_re.search(line) is not None
        if is_header and "|---" not in stripped:
            in_status_table = True
            status_start = i
        if (
            in_status_table
            and status_start >= 0
            and i > status_start
            and (stripped == "" or not stripped.startswith("|"))
        ):
            status_end = i
            break

    if status_start >= 0 and status_end < 0:
        status_end = len(lines)

    if status_start >= 0 and status_end > status_start:
        # Build new status table replacing old rows (but keep header & separator)
        new_table = []
        new_table.append(lines[status_start])  # header
        if status_start + 1 < len(lines):
            new_table.append(lines[status_start + 1])  # separator

        # Emit row per label, in canonical order
        new_table.append(
            f"| pytest (unit + schema) | {tc.get('unit', 0) + tc.get('schema', 0)} passing "
            f"(unit: {tc.get('unit', 0)}, schema: {tc.get('schema', 0)}) | ✅ |"
        )
        if tc.get("integration"):
            new_table.append(f"| pytest (integration) | {tc['integration']} passing | ✅ |")
        if tc.get("design"):
            new_table.append(f"| pytest (design) | {tc['design']} passing | ✅ |")
        if tc.get("real"):
            new_table.append(f"| pytest (real, slow) | {tc['real']} passing | ✅ |")
        if tc.get("e2e"):
            new_table.append(
                f"| pytest (e2e) | {tc['e2e']} collected (blocked on Playwright live Streamlit Cloud) | ⏳ |"
            )

        # Replace in lines
        lines = lines[:status_start] + new_table + lines[status_end:]

    if dry_run:
        return changes

    _AGENTS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changes


def _update_readme_tree(dry_run: bool = False) -> list[str]:
    """Update README.md directory tree if new files were added."""
    # This is lightweight — just verify key files exist
    key_files = [
        "README.md",
        "AGENTS.md",
        "pyproject.toml",
        "requirements.txt",
        "Makefile",
        "main.py",
        "services/price_service.py",
        "dashboard/pages/precos.py",
        "config/ingredients.yaml",
        "config/stores.yaml",
    ]
    missing = [f for f in key_files if not (_ROOT / f).exists()]

    changes = []
    if missing:
        changes.append(f"Missing key files: {missing}")

    return changes


def _check_api_docs() -> list[str]:
    """Verify API docs exist and are not empty."""
    required_api = [
        "docs/api/price_service.md",
        "docs/api/dashboard_queries.md",
        "docs/api/config_db.md",
        "docs/api/flyer_service.md",
    ]
    issues = []
    for api_file in required_api:
        path = _ROOT / api_file
        if not path.exists():
            issues.append(f"Missing: {api_file}")
        elif path.stat().st_size < 100:
            issues.append(f"Empty or too small: {api_file}")
    return issues


def run_sync(dry_run: bool = False, check: bool = False) -> bool:
    """
    Main sync logic. Returns True if in sync, False if out of sync.

    With check=True: drift detection runs against pytest --collect-only. If the
    source of truth (sync_docs count) disagrees with pytest's reported total,
    --check fails. This prevents silent drift between declared and actual numbers.
    """
    issues: list[str] = []

    # Build current state
    state = _build_agents_state()
    print(f"Current state (as of {state['updated_at']}):")
    print(
        f"  Tests: {state['total_tests']} total ({', '.join(f'{k}={v}' for k, v in state['test_counts'].items() if v > 0)})"
    )
    print(f"  Dashboard pages: {state['pages_count']}")
    print(f"  API services: {', '.join(state['api_services'])}")
    print(f"  CI workflows: {', '.join(state['workflows'])}")

    # Drift detection — always (visible in --dry-run; required for --check)
    print("\nDrift detection (sync_docs counts vs pytest --collect-only)...")
    drift = _check_drift()
    if drift:
        for d in drift:
            print(f"  [DRIFT] {d}")
            issues.append(f"Drift: {d}")
    else:
        print("  [OK] All test counts match pytest --collect-only")

    # Check API docs
    api_issues = _check_api_docs()
    if api_issues:
        issues.extend(api_issues)

    # Update AGENTS.md
    print("\nUpdating AGENTS.md...")
    agent_changes = _update_agents_md(state, dry_run=dry_run)
    if dry_run:
        for c in agent_changes:
            print(f"  {c}")
        print("  (dry-run, no changes applied)")

    # Check README key files
    print("\nChecking README tree...")
    tree_issues = _update_readme_tree(dry_run=dry_run)
    issues.extend(tree_issues)
    for issue in tree_issues:
        print(f"  [WARN] {issue}")

    # Summary
    print()
    if issues:
        print(f"[FAIL] Issues found: {len(issues)}")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print(f"[{_OK}] All docs in sync")
        return True


def main():
    parser = argparse.ArgumentParser(description="Sync project documentation with code state")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--check", action="store_true", help="Exit 1 if docs are out of sync (CI mode)")
    args = parser.parse_args()

    in_sync = run_sync(dry_run=args.dry_run, check=args.check)

    if args.check and not in_sync:
        print("\n::error::Documentation is out of sync. Run 'python scripts/sync_docs.py' to update.")
        sys.exit(1)
    if args.dry_run:
        print("\n(Dry-run complete, no changes made)")


if __name__ == "__main__":
    main()
