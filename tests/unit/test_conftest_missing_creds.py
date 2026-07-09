"""
Regression test for tests/conftest.py:_has_real_db().

Garante via AST que _has_real_db() NAO exige SUPABASE_DB_PASSWORD (legado psycopg2/5432).
Conforme AGENTS.md regra #3, o projeto usa SOMENTE exec_sql_query RPC porta 443,
entao basta SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (ou ANON_KEY).
"""

from __future__ import annotations

import ast
from pathlib import Path


CONFTEST_PATH = Path(__file__).resolve().parent.parent.parent / "tests" / "conftest.py"


def _parse_conftest():
    """Parseia tests/conftest.py como AST."""
    return ast.parse(CONFTEST_PATH.read_text(encoding="utf-8"))


def _find_function(tree, name):
    """Encontra funcao por nome."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _body_without_docstring(func_node):
    """Retorna source do body excluindo docstring (Expr/Constant)."""
    return "\n".join(
        ast.unparse(stmt)
        for stmt in func_node.body
        if not (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        )
    )


def test_has_real_db_body_nao_referencia_supabase_db_password():
    """Garante que o BODY de _has_real_db NAO checa SUPABASE_DB_PASSWORD.

    Previne regressao: helper antigo exigia DB_PASSWORD, skipando 112 testes
    em CI sem essa credencial (cf. AGENTS.md regra #3).
    A docstring pode mencionar DB_PASSWORD como contexto historico e ai OK.
    """
    tree = _parse_conftest()
    func = _find_function(tree, "_has_real_db")
    assert func is not None, "Funcao _has_real_db nao encontrada em tests/conftest.py"
    body_src = _body_without_docstring(func)
    assert "SUPABASE_DB_PASSWORD" not in body_src, (
        "_has_real_db() body ainda referencia SUPABASE_DB_PASSWORD.\n"
        "Conforme AGENTS.md regra #3, isso e legado psycopg2/5432.\n"
        f"Body atual:\n{body_src}"
    )


def test_has_real_db_aceita_service_role_e_anon():
    """_has_real_db aceita SERVICE_ROLE_KEY OU ANON_KEY (fallback chain)."""
    tree = _parse_conftest()
    func = _find_function(tree, "_has_real_db")
    body_src = _body_without_docstring(func)
    assert "SUPABASE_SERVICE_ROLE_KEY" in body_src
    assert "SUPABASE_ANON_KEY" in body_src


def test_has_real_db_requer_supabase_url():
    """"_has_real_db continua exigindo SUPABASE_URL como condicao necessaria."""
    tree = _parse_conftest()
    func = _find_function(tree, "_has_real_db")
    body_src = _body_without_docstring(func)
    assert "SUPABASE_URL" in body_src


def test_has_real_db_mantem_sanity_check_project_ref():
    """Sanity check: URL com project ref < 10 chars deve retornar False."""
    tree = _parse_conftest()
    func = _find_function(tree, "_has_real_db")
    body_src = _body_without_docstring(func)
    assert "proj = url.split" in body_src
    assert "len(proj)" in body_src


def test_pytest_collection_modifyitems_skipa_quando_sem_real_db():
    """Auto-skip do conftest usa _has_real_db() e NAO exige mais DB_PASSWORD.

    Conforme AGENTS.md regra #11 (RPR), garantir aqui a regra de negocio.
    """
    tree = _parse_conftest()
    func = _find_function(tree, "pytest_collection_modifyitems")
    assert func is not None, "pytest_collection_modifyitems nao encontrada"
    body_src = _body_without_docstring(func)
    assert "_has_real_db()" in body_src
    assert "pytest.mark.skip" in body_src
    assert "SUPABASE_DB_PASSWORD" not in body_src, (
        "pytest_collection_modifyitems NUNCA deve referenciar SUPABASE_DB_PASSWORD "
        "(legado psycopg2/5432)."
    )
