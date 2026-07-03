"""Source of truth: extract actual project state from code.

Returns serializable dict with:
- test_counts, total_tests
- pages, pages_count
- services_api, api_services
- workflows, workflows_count
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_GIT_DIR = _ROOT / ".git"
_SYNC_PAT = __import__("re").compile(r"<Function\s+test_")
_ASYNC_PAT = __import__("re").compile(r"<Coroutine\s+test_")
_TEST_DIRS = [
    ("tests/unit", "unit"),
    ("tests/schema", "schema"),
    ("tests/integration", "integration"),
    ("tests/e2e", "e2e"),
    ("tests/real", "real"),
    ]


def count_tests() -> dict[str, int]:
    """Count tests per category using pytest --collect-only."""
    result = {}
    for test_path, label in _TEST_DIRS:
        full_path = _ROOT / test_path
        if not full_path.exists():
            continue
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(full_path), "--collect-only", "-q", "--no-header"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, cwd=str(_ROOT),
            )
            sync_count = len(_SYNC_PAT.findall(proc.stdout))
            async_count = len(_ASYNC_PAT.findall(proc.stdout))
            result[label] = sync_count + async_count
        except Exception:
            result[label] = 0
    return result


def _extract_pages() -> list[tuple[str, str, str]]:
    """Extract PAGES from dashboard/components/layout.py."""
    layout_path = _ROOT / "dashboard" / "components" / "layout.py"
    content = layout_path.read_text(encoding="utf-8")
    pages: list[tuple[str, str, str]] = []
    in_block = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "PAGES = [":
            in_block = True
            continue
        if in_block:
            if stripped == "]":
                break
            m = __import__("re").match(
                r'\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']',
                line,
            )
            if m:
                pages.append((m.group(1), m.group(2), m.group(3)))
    return pages


def _extract_services_api() -> dict[str, list[str]]:
    """Extract public functions from service modules."""
    api: dict[str, list[str]] = {}
    services_dir = _ROOT / "services"
    for py_file in services_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        functions: list[str] = []
        content = py_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            m = __import__("re").match(r"^def\s+(\w+)\s*\(", line)
            if m:
                fn = m.group(1)
                if not fn.startswith("_"):
                    functions.append(fn)
        if functions:
            api[py_file.stem] = sorted(functions)
    return api


def _extract_workflows() -> list[str]:
    wf_dir = _ROOT / ".github" / "workflows"
    if not wf_dir.exists():
        return []
    return sorted([f.stem for f in wf_dir.glob("*.yml")])


def _count_dashboard_pages() -> int:
    pages_dir = _ROOT / "dashboard" / "pages"
    if not pages_dir.exists():
        return 0
    return sum(
        1 for f in pages_dir.iterdir() if f.suffix == ".py" and f.stem != "__init__"
    )


def build_truth() -> dict:
    """Build current project state dict — single source of truth."""
    tc = count_tests()
    pages = _extract_pages()
    services_api = _extract_services_api()
    workflows = _extract_workflows()
    total_tests = sum(tc.values())

    return {
        "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "total_tests": total_tests,
        "test_counts": tc,
        "pages": pages,
        "pages_count": _count_dashboard_pages(),
        "services_api": services_api,
        "workflows": workflows,
        "workflows_count": len(workflows),
        "api_services": sorted(services_api.keys()),
    }
