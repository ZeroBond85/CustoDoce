"""Testa a fiação do admin/app.py sem executar Streamlit.

Pega regressões como a TypeError que estava em produção desde FASE 8
(render_login() chamado com argumento que não aceita).

Testa:
- Todos os módulos de página importam sem erro
- Todas as funções de página têm a assinatura esperada (0 args, sem return obrigatório)
- PAGE_FUNCTIONS contém entrada para cada módulo importado
- Nenhuma página referenciada em PAGE_FUNCTIONS está faltando
- render_login() é chamado sem argumento
"""

import inspect
from types import FunctionType


def test_all_page_modules_import():
    """Cada page module importa sem erro."""
    from dashboard.pages import (
        visao_geral,
        precos,
        historico,
        flyers,
        revisao,
        fontes,
        ranking,
        insights,
        lojas,
        ingredientes,
        alertas,
        scrapers,
        scraper_health,
        relatorios,
        config,
        calculadora,
        diagnostico,
        promocoes,
        capacity_planning,
    )

    assert visao_geral
    assert precos
    assert historico
    assert flyers
    assert revisao
    assert fontes
    assert ranking
    assert insights
    assert lojas
    assert ingredientes
    assert alertas
    assert scrapers
    assert scraper_health
    assert relatorios
    assert config
    assert calculadora
    assert diagnostico
    assert promocoes
    assert capacity_planning


def test_render_login_signature():
    """render_login() não aceita argumentos.

    Regressão: TypeError que quebrou produção (FASE 8 introduziu
    render_login(ADMIN_PASSWORD) mas função espera 0 args).
    """
    from dashboard.login_page import render_login

    sig = inspect.signature(render_login)
    # Nenhum parâmetro obrigatório
    assert len([p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]) == 0, (
        f"render_login() deve ser chamavel sem argumentos, assinatura: {sig}"
    )


def test_login_page_import():
    """login_page importa sem erro."""
    from dashboard import login_page

    assert hasattr(login_page, "render_login")
    assert callable(login_page.render_login)


def test_app_import_and_registry():
    """admin/app.py importa e PAGE_FUNCTIONS tem todas as entradas."""
    import admin.app  # noqa: F401 — import necessario para testar modulo sem erros
    from admin.app import PAGE_FUNCTIONS

    for key, fn in PAGE_FUNCTIONS.items():
        assert isinstance(fn, FunctionType), f"{key} não é função: {fn}"
        assert callable(fn), f"{key} não é callable: {fn}"


def test_all_page_functions_have_zero_required_args():
    """Toda função de página deve ser chamavel sem argumentos obrigatórios."""
    from admin.app import PAGE_FUNCTIONS

    for key, fn in PAGE_FUNCTIONS.items():
        sig = inspect.signature(fn)
        required = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
        assert len(required) == 0, f"{key} ({fn.__name__}) tem {len(required)} parametros obrigatorios: {sig}"


def test_main_does_not_call_render_login_with_args():
    """Verifica que main() chama render_login() sem argumentos.

    Lê o fonte e confirma que não há render_login(....).
    """
    import ast

    with open("admin/app.py", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Name) and call.func.id == "render_login":
                assert len(call.args) == 0, (
                    f"render_login() chamado com {len(call.args)} argumento(s) em "
                    f"admin/app.py linha {node.lineno}: {ast.unparse(node)}"
                )


def test_no_page_function_called_directly_with_args():
    """Nenhuma render_*() é chamada diretamente com argumento em app.py.

    Em app.py, páginas são chamadas via PAGE_FUNCTIONS[current_page]().
    Se alguém adicionar render_precos(algo) direto, isso falha.
    """
    import ast

    with open("admin/app.py", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    page_fn_names = {
        "render_visao_geral",
        "render_precos",
        "render_historico",
        "render_flyers",
        "render_revisao",
        "render_fontes",
        "render_ranking",
        "render_insights",
        "render_lojas",
        "render_ingredientes",
        "render_alertas",
        "render_scrapers",
        "render_scraper_health",
        "render_relatorios",
        "render_config",
        "render_calculadora",
        "render_diagnostico",
        "render_promocoes",
        "render_capacity_planning",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Name) and call.func.id in page_fn_names:
                assert len(call.args) == 0, (
                    f"{call.func.id}() chamado com {len(call.args)} args em "
                    f"admin/app.py linha {node.lineno}: {ast.unparse(node)}"
                )


def test_promocoes_registered_in_page_functions():
    """Promocoes page was in Fase 8 as orphan; Sprint 7 integrates it."""
    from admin.app import PAGE_FUNCTIONS

    assert "promocoes" in PAGE_FUNCTIONS
    assert callable(PAGE_FUNCTIONS["promocoes"])


def test_menu_groups_structure():
    """MENU_GROUPS contém 5 grupos cobrindo todas as 19 páginas."""
    from admin.app import MENU_GROUPS, PAGE_FUNCTIONS

    expected_groups = {"📊 Painel", "📈 Análises", "📦 Cadastros", "🤖 Operações", "🔧 Ferramentas"}
    actual_groups = set(MENU_GROUPS.keys())
    assert expected_groups.issubset(actual_groups), (
        f"Grupos faltando: {expected_groups - actual_groups}"
    )

    seen_pages: set[str] = set()
    for group_pages in MENU_GROUPS.values():
        for entry in group_pages:
            assert len(entry) == 3, f"Tupla invalida: {entry}"
            label, icon, page_id = entry
            seen_pages.add(page_id)
            assert page_id in PAGE_FUNCTIONS, f"Pagina {page_id} nao esta em PAGE_FUNCTIONS"

    assert seen_pages == set(PAGE_FUNCTIONS.keys()), (
        f"Paginas faltando nos grupos: {set(PAGE_FUNCTIONS.keys()) - seen_pages}; "
        f"Paginas extras: {seen_pages - set(PAGE_FUNCTIONS.keys())}"
    )


def test_layout_pmenu_groups_sync_with_admin_app():
    """Both layout.py and admin/app.py import MENU_GROUPS from navigation_config (single source of truth)."""
    from admin.app import MENU_GROUPS as ADMIN_MENU
    from dashboard.navigation_config import MENU_GROUPS as NAV_MENU

    assert ADMIN_MENU is NAV_MENU, "admin.app.MENU_GROUPS must be the same object as navigation_config.MENU_GROUPS"
    assert len(ADMIN_MENU) > 0, "MENU_GROUPS must not be empty"
