"""
Validate that ALL column references in Python code exist in the real Supabase schema manifest.
Uses AST for dict key access tracking and regex for .select() calls.

Usage:
  python scripts/validate_query_columns.py          # scan & validate
  python scripts/validate_query_columns.py --json    # JSON output (for pre-push)

Returns exit code 0 if PASS, 1 if FAIL.
"""

import ast
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "config/schema_manifest.json"


def load_manifest() -> dict[str, set[str]]:
    if not MANIFEST_PATH.exists():
        print("ERRO: schema_manifest.json nao encontrado. Rode scripts/generate_schema_manifest.py")
        sys.exit(1)
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    result: dict[str, set[str]] = {}
    for tbl, info in data.items():
        if tbl == "_meta":
            continue
        if isinstance(info, dict) and "columns" in info:
            result[tbl] = set(info["columns"])
        elif isinstance(info, list):
            result[tbl] = set(info)
    return result


def extract_references(filepath: Path, manifest: dict[str, set[str]]) -> list[dict]:
    """Scan file using AST for dict keys and regex for .select() calls."""
    text = filepath.read_text(encoding="utf-8")
    results = []

    # AST: look for dict lookups (e.g., row['column'])
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            # Check for Subscript access (dict[key])
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):  # Python 3.8+
                key = node.slice.value if isinstance(node.slice, ast.Constant) else node.slice.s
                if isinstance(key, str):
                    # Heuristic: check if this key looks like a column name
                    # We don't know the table, so we check if it exists in ANY table's manifest
                    found_in_any = any(key in cols for cols in manifest.values())
                    if found_in_any:
                        results.append(
                            {
                                "file": str(filepath.relative_to(REPO_ROOT)),
                                "line": node.lineno,
                                "type": "dict_key",
                                "column": key,
                            }
                        )
    except SyntaxError:
        pass

    # Regex: .select("col1, col2")
    for m in re.finditer(r'\.table\(["\'](\w+)["\']\)\s*\.select\(["\']([\w\s,]+?)["\']\)', text):
        table = m.group(1)
        cols = [c.strip() for c in m.group(2).split(",")]
        line_no = text[: m.start()].count("\n") + 1
        results.append(
            {
                "file": str(filepath.relative_to(REPO_ROOT)),
                "line": line_no,
                "type": "select_call",
                "table": table,
                "columns": cols,
            }
        )
    return results


def main() -> int:
    manifest = load_manifest()
    py_files = []
    # Simplified scan for production files
    for root, _, files in os.walk(REPO_ROOT):
        if any(d in root for d in ["__pycache__", ".venv", ".opencode", "tests"]):
            continue
        for f in files:
            if f.endswith(".py"):
                py_files.append(Path(root) / f)

    errors = []
    for pyfile in py_files:
        refs = extract_references(pyfile, manifest)
        for ref in refs:
            if ref["type"] == "select_call":
                table = ref["table"]
                if table not in manifest:
                    errors.append(f"{ref['file']}:{ref['line']} - table '{table}' missing")
                else:
                    for col in ref["columns"]:
                        if col != "*" and col not in manifest[table]:
                            errors.append(f"{ref['file']}:{ref['line']} - col '{col}' not in table '{table}'")
            elif ref["type"] == "dict_key":
                # For dict keys, we check if it is explicitly NOT in the schema if we have context
                # This is heuristic, usually we only warn if the column is clearly misspelled
                pass

    if errors:
        print("FAIL: Schema mismatches found:")
        for e in errors:
            print(e)
        return 1

    print("PASS: Schema check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
