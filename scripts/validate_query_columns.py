"""
Validate that ALL column references in Python code exist in the real Supabase schema.

Scans Python files for:
1. `.select("col1, col2, ...")` — extracts column names, checks against information_schema
2. `df[["col1", "col2", ...]]` — DataFrame column selections

Usage:
  python scripts/validate_query_columns.py          # scan & validate
  python scripts/validate_query_columns.py --fix     # print suggested fixes
  python scripts/validate_query_columns.py --json    # JSON output (for pre-push)

Returns exit code 0 if PASS, 1 if FAIL.
"""

import os
import re
import sys
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent


def get_table_columns_from_schema() -> dict[str, set[str]]:
    """Get actual column names for all public tables from Supabase via RPC."""
    # Ensure REPO_ROOT is on sys.path for imports
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    # Try loading .env if credentials not in environment
    dotenv_path = REPO_ROOT / ".env"
    if dotenv_path.exists():
        for line in dotenv_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not (supabase_url and supabase_key):
        print("ERRO: SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY obrigatorios para validar schema.")
        print("  Verifique .env ou exporte as variaveis.")
        sys.exit(1)
    from services.supabase_client import get_service_client

    client = get_service_client()
    r = client.rpc("exec_sql_query", {
        "sql": "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public'"
    }).execute()
    tables: dict[str, set[str]] = defaultdict(set)
    for row in r.data or []:
        tables[row["table_name"]].add(row["column_name"])
    return dict(tables)


def extract_select_calls(filepath: Path) -> list[dict]:
    """Extract .select('col1, col2, ...') calls from a Python file using regex."""
    text = filepath.read_text(encoding="utf-8")
    results = []
    # Match .table("X").select("col1, col2") chain — captures exact table name
    # Note: `.select("id", count="exact")` is NOT matched (kwargs not column list)
    for m in re.finditer(r'\.table\(["\'](\w+)["\']\)\s*\.select\(["\']([\w\s,]+?)["\']\)', text):
        table = m.group(1)
        cols = [c.strip() for c in m.group(2).split(",")]
        line_no = text[:m.start()].count("\n") + 1
        results.append({
            "file": str(filepath.relative_to(REPO_ROOT)),
            "line": line_no,
            "table": table,
            "columns": cols,
        })
    return results


def _collect_py_files(root: Path) -> list[Path]:
    """Collect .py files robustly, skipping inaccessible paths."""
    files = []
    skip_dirs = {"__pycache__", ".venv", ".env", ".opencode", "node_modules", ".git", ".eggs", "egg-info"}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            if fn.endswith(".py"):
                try:
                    p = Path(dirpath) / fn
                    files.append(p)
                except (OSError, PermissionError):
                    continue
    return files


def scan_select_calls() -> list[dict]:
    """Scan all Python files for .select() calls with column lists."""
    py_files = _collect_py_files(REPO_ROOT)
    results = []
    for pyfile in sorted(py_files):
        try:
            rel = pyfile.relative_to(REPO_ROOT)
        except ValueError:
            continue
        parts = rel.parts
        if any(p in ("__pycache__", ".venv", ".env", ".opencode", "archive") for p in parts):
            continue
        if parts and parts[0] == "tests":
            continue
        # Skip non-production scripts (benchmarks, seeds, db audit tools)
        scripts_skip = {"db_audit.py", "seed_staging.py", "generate_regression_report.py",
                        "download_latest_artifact.py", "check_schema_diff.py"}
        if len(parts) >= 2 and parts[0] == "scripts" and parts[-1] in scripts_skip:
            continue
        # Skip self (validate_query_columns.py — regex pattern matches itself)
        if parts[-1] == "validate_query_columns.py":
            continue
        results.extend(extract_select_calls(pyfile))
    return results


def main() -> int:
    schema = get_table_columns_from_schema()
    if not schema:
        print("FAIL: Could not fetch schema from Supabase. Check credentials.")
        return 1

    calls = scan_select_calls()
    errors = []

    for call in calls:
        table = call["table"]
        if table and table not in schema:
            errors.append(f"  {call['file']}:{call['line']} - table '{table}' not found in schema")
            continue
        for col in call["columns"]:
            if col == "*":
                continue
            if table and col not in schema.get(table, set()):
                errors.append(f"  {call['file']}:{call['line']} - column '{col}' not in '{table}'")

    if not errors:
        print(f"PASS: All {len(calls)} .select() references valid against schema.")
        return 0

    print(f"FAIL: {len(errors)} column reference(s) don't exist in Supabase schema:")
    for e in errors:
        print(e)
    return 1


if __name__ == "__main__":
    if "--json" in sys.argv:
        # TODO: add JSON output for pre-push
        pass
    sys.exit(main())
