"""Unit tests for scripts/validate_db_schema.py — anti-no-op guarantees.

Historico: o script ja foi um no-op perfeito (arquivo de UMA linha com shebang
#! que engolia todo o codigo como comentario). Estes testes garantem que ele
NUNCA volte a ser no-op: devem falhar se o script virar vazio/ilegivel.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

SCRIPT_PATH = Path("scripts/validate_db_schema.py")


def _read_script() -> str:
    with open(SCRIPT_PATH, encoding="utf-8-sig") as f:
        return f.read()

class TestAntiNoOp:
    def test_script_has_multiple_lines(self):
        content = _read_script()
        assert content.count("\n") > 50, (
            "script voltou a ser single-line no-op (arquivo minificado)"
        )

    def test_script_parses_as_python(self):
        tree = ast.parse(_read_script())
        funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        assert funcs, "nenhuma funcao definida — script vazio/no-op"

    def test_script_has_main_and_exit(self):
        content = _read_script()
        assert "def main()" in content
        assert "sys.exit(main())" in content

    def test_script_has_required_validation_functions(self):
        tree = ast.parse(_read_script())
        funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for expected in ["validate_tables", "validate_columns", "validate_constraints"]:
            assert expected in funcs, f"funcao {expected} ausente"

    def test_script_uses_rpc_443(self):
        content = _read_script()
        assert "exec_sql_query" in content, "deve consultar via RPC exec_sql_query (porta 443)"
        assert "psycopg2" not in content, "NUNCA deve usar psycopg2 (AGENTS.md regra #4)"

    def test_script_fails_without_creds(self):
        # Sem credenciais, get_client() deve abortar com exit != 0
        import subprocess

        env = {"PATH": "/usr/bin:/bin", "HOME": "/root"}
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
        )
        assert result.returncode != 0, (
            "script deveria falhar sem SUPABASE_URL/SERVICE_ROLE_KEY"
        )

    def test_manifest_is_source_of_truth(self):
        import json

        with open("config/schema_manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        tables = {k for k in manifest if k != "_meta"}
        content = _read_script()
        assert "load_manifest" in content
        assert "schema_manifest.json" in content
        assert len(tables) >= 15, "manifest deveria ter >= 15 tabelas"


class TestManifestHealth:
    def test_manifest_has_expected_tables(self):
        import json

        with open("config/schema_manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        tables = {k for k in manifest if k != "_meta"}
        for t in ["prices", "stores", "ingredients", "review_queue", "v_latest_prices"]:
            assert t in tables, f"tabela {t} ausente do manifest"

    def test_manifest_tables_have_columns(self):
        import json

        with open("config/schema_manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        for table, spec in manifest.items():
            if table == "_meta":
                continue
            assert spec.get("columns"), f"{table} sem colunas no manifest"
