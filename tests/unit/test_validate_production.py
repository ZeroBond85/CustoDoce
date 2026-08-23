"""Unit tests para scripts/validate_production.py (PR-04 — audit item #3).

O script legado usava psycopg2 direto (porta 5432, bloqueada no CI — AGENTS
regra #4) com colunas hardcoded desatualizadas. Agora reutiliza as queries
bulk estáticas de validate_db_schema.py via RPC 443 e mantém as seções HTTP.
Estes testes travam a política source-level do rewrite.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

SCRIPT = Path("scripts/validate_production.py")

# Legados removidos neste PR — não podem ressuscitar.
DELETED_SCRIPTS = ["scripts/check_schema_diff.py", "scripts/run_full_migration.py"]


def _read() -> str:
    return SCRIPT.read_text(encoding="utf-8")


class TestNoPsycopg2Policy:
    def test_no_psycopg2_import(self):
        tree = ast.parse(_read())
        modules: set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                modules.update(alias.name for alias in n.names)
            elif isinstance(n, ast.ImportFrom):
                modules.add(n.module or "")
        assert not any("psycopg2" in m for m in modules), "regra AGENTS #4: NUNCA psycopg2"

    def test_reuses_bulk_sql_from_validate_db_schema(self):
        content = _read()
        assert "from scripts.validate_db_schema import" in content
        for const in ("SQL_COLUMNS", "SQL_FUNCTIONS"):
            assert const in content

    def test_smoke_queries_are_static_literals(self):
        tree = ast.parse(_read())
        assigns = {
            n.targets[0].id: n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
        }
        value = assigns.get("SMOKE_QUERIES")
        assert isinstance(value, ast.Tuple), "SMOKE_QUERIES deve ser tupla literal"
        for elt in value.elts:
            assert isinstance(elt, ast.Tuple)
            for item in elt.elts:
                assert isinstance(item, ast.Constant), "queries de smoke devem ser literais"

    def test_has_main_and_exit_code_semantics(self):
        content = _read()
        assert "def main()" in content
        assert 'sys.exit(0 if results["fail"] == 0 else 1)' in content

    def test_http_sections_preserved(self):
        content = _read()
        for marker in ("custodoce.streamlit.app", "actions/workflows", "GITHUB_TOKEN"):
            assert marker in content


class TestLegacyScriptsDeleted:
    def test_superseded_scripts_do_not_exist(self):
        repo_root = Path(__file__).resolve().parent.parent.parent
        for rel in DELETED_SCRIPTS:
            assert not (repo_root / rel).exists(), (
                f"{rel} foi superseded (validate_db_schema/deploy_database) e removido no PR-04"
            )

    def test_docs_reference_canonical_tools(self):
        docs = (Path(__file__).resolve().parent.parent.parent / "docs" / "deployment-staging.md").read_text(
            encoding="utf-8"
        )
        assert "check_schema_diff" not in docs
        assert "validate_db_schema" in docs
