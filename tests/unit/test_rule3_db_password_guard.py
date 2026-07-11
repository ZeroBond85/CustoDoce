"""Guard test for AGENTS.md Regra #3: NUNCA psycopg2/SUPABASE_DB_PASSWORD.

Garante via AST que nenhum teste importe ou use SUPABASE_DB_PASSWORD.
Rodar em ci.yml job lint.
"""

from __future__ import annotations

import ast
from pathlib import Path


def _find_python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if p.is_file()]


def _has_db_password_usage(tree: ast.AST) -> bool:
    """Check if AST node references SUPABASE_DB_PASSWORD."""
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "SUPABASE_DB_PASSWORD" in n.value:
            return True
        if isinstance(n, ast.Name) and n.id == "SUPABASE_DB_PASSWORD":
            return True
    return False


def test_no_supabase_db_password_in_tests():
    """Garante que nenhum teste use SUPABASE_DB_PASSWORD (Regra #3)."""
    test_dirs = [
        Path("tests/unit"),
        Path("tests/integration"),
        Path("tests/e2e"),
        Path("tests/real"),
        Path("tests/schema"),
    ]

    # Arquivos permitidos a referenciar SUPABASE_DB_PASSWORD (testam a regra)
    allowed_files = {
        Path("tests/unit/test_conftest_missing_creds.py"),
        Path("tests/unit/test_rule3_db_password_guard.py"),
    }

    violations = []
    for test_dir in test_dirs:
        if not test_dir.exists():
            continue
        for py_file in _find_python_files(test_dir):
            if py_file in allowed_files:
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(py_file))
                for n in ast.walk(tree):
                    if isinstance(n, ast.Constant) and isinstance(n.value, str) and "SUPABASE_DB_PASSWORD" in n.value:
                        violations.append(
                            f"{py_file}:{n.lineno}: string literal contains SUPABASE_DB_PASSWORD"
                        )
                    if isinstance(n, ast.Name) and n.id == "SUPABASE_DB_PASSWORD":
                        violations.append(
                            f"{py_file}:{n.lineno}: Name SUPABASE_DB_PASSWORD referenced"
                        )
            except SyntaxError:
                pass  # Skip files with syntax errors

    if violations:
        raise AssertionError(
            "Regra #3 violada: SUPABASE_DB_PASSWORD encontrado em testes:\n" + "\n".join(violations)
        )


def test_no_psycopg2_import_in_tests():
    """Garante que nenhum teste importe psycopg2 (Regra #3)."""
    test_dirs = [
        Path("tests/unit"),
        Path("tests/integration"),
        Path("tests/e2e"),
        Path("tests/real"),
        Path("tests/schema"),
    ]

    violations = []
    for test_dir in test_dirs:
        if not test_dir.exists():
            continue
        for py_file in _find_python_files(test_dir):
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(py_file))
                for n in ast.walk(tree):
                    if isinstance(n, ast.Import):
                        for alias in n.names:
                            if alias.name == "psycopg2" or alias.name.startswith("psycopg2."):
                                violations.append(f"{py_file}: import psycopg2")
                    if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("psycopg2"):
                        violations.append(f"{py_file}: from {n.module} import ...")
            except SyntaxError:
                pass

    if violations:
        raise AssertionError(
            "Regra #3 violada: psycopg2 importado em testes:\n" + "\n".join(violations)
        )


if __name__ == "__main__":
    test_no_supabase_db_password_in_tests()
    test_no_psycopg2_import_in_tests()
    print("OK: Regra #3 guards passed")
