"""
E2E Interactions - testa widgets/interacoes em cada pagina do dashboard.

Auto-adaptavel: usa MENU_GROUPS como fonte unica de paginas.
Se pagina for adicionada/removida automaticamente.
Pagina sem interacoes registradas: navega + check de erros + skip com aviso.

Disparo: Teste_Full_Manual workflow (workflow_dispatch).
"""
import sys
from pathlib import Path

_repo_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _repo_root)

import pytest

from dashboard.navigation_config import MENU_GROUPS
from .test_e2e_real import check_for_errors, wake_if_sleeping

BASE_URL = "http://localhost:8501"
ADMIN_PASSWORD = ""

PAGES = [(page_id, label) for _group, group_pages in MENU_GROUPS.items() for label, _icon, page_id in group_pages]


def _select_first_option(app, key_substring: str):
    sel = app.locator("select").filter(has=app.locator(f"[key*='{key_substring}']")).first
    if sel.count() > 0:
        sel.select_option(index=1)
        app.wait_for_timeout(1000)


def _adjust_slider(app, label: str, value: int):
    slider = app.locator("input[type='range']").filter(has=app.locator(f"label:has-text('{label}')")).first
    if slider.count() > 0:
        slider.fill(str(value))
        app.wait_for_timeout(1000)


def _click_first_multiselect(app, label: str):
    sel = app.locator("[data-testid='stMultiSelect']").filter(has=app.locator(f"label:has-text('{label}')")).first
    if sel.count() > 0:
        sel.click()
        app.wait_for_timeout(500)
        app.locator("div[role='option']").first.click()
        app.wait_for_timeout(500)


def _click_button(app, text: str):
    btn = app.locator(f"button:has-text('{text}')").first
    if btn.count() > 0:
        btn.click()
        app.wait_for_timeout(1500)


def _toggle_checkbox(app, label: str):
    cb = app.locator("input[type='checkbox']").filter(has=app.locator(f"label:has-text('{label}')")).first
    if cb.count() > 0:
        cb.click()
        app.wait_for_timeout(500)


def _test_precos_interactions(app, page):
    _select_first_option(app, "precos_ingredient")
    _select_first_option(app, "precos_store")
    _select_first_option(app, "precos_tier")


def _test_historico_interactions(app, page):
    _select_first_option(app, "hist_ingredient")
    _adjust_slider(app, "Período", 30)
    _toggle_checkbox(app, "Apenas preços válidos")
    _select_first_option(app, "hist_chart")


def _test_promocoes_interactions(app, page):
    _click_first_multiselect(app, "Loja")
    _click_first_multiselect(app, "Ingrediente")
    _select_first_option(app, "Ordenar por")


def _test_ranking_interactions(app, page):
    tabs = app.locator("button[data-baseweb='tab']")
    if tabs.count() > 1:
        tabs.nth(1).click()
        app.wait_for_timeout(1500)
    _adjust_slider(app, "Período (dias)", 60)


def _test_revisao_interactions(app, page):
    slider = app.locator("input[type='range']").first
    if slider.count() > 0:
        slider.fill("0.5")
        app.wait_for_timeout(1000)
    approve = app.locator("button:has-text('Aprovar')").first
    if approve.count() > 0:
        approve.click()
        confirm = app.locator("button:has-text('Sim, aprovar')").first
        if confirm.count() > 0:
            confirm.click()
            app.wait_for_timeout(2000)


def _test_calculadora_interactions(app, page):
    select = app.locator("select, [data-testid='stSelectbox'] select").first
    if select.count() > 0:
        select.select_option(index=1)
        app.wait_for_timeout(2000)
        select.select_option(index=2)
        app.wait_for_timeout(2000)
        select.select_option(index=0)
        app.wait_for_timeout(1000)


def _test_diagnostico_interactions(app, page):
    btn = app.locator("button:has-text('Executar Benchmarks')").first
    if btn.count() > 0:
        btn.click()
        app.wait_for_timeout(10000)


def _test_relatorios_interactions(app, page):
    tabs = app.locator("button[data-baseweb='tab']")
    if tabs.count() > 1:
        tabs.nth(1).click()
        app.wait_for_timeout(1000)
    _toggle_checkbox(app, "Incluir promoções")
    _click_button(app, "Testar SMTP")
    _click_button(app, "Testar Telegram")


def _test_lojas_interactions(app, page):
    tabs = app.locator("button[data-baseweb='tab']")
    if tabs.count() > 1:
        tabs.nth(1).click()
        app.wait_for_timeout(1000)


def _test_ingredientes_interactions(app, page):
    tabs = app.locator("button[data-baseweb='tab']")
    if tabs.count() > 1:
        tabs.nth(1).click()
        app.wait_for_timeout(1000)
    _select_first_option(app, "Categoria")
    _click_button(app, "Testar")


def _test_alertas_interactions(app, page):
    tabs = app.locator("button[data-baseweb='tab']")
    if tabs.count() > 1:
        tabs.nth(1).click()
        app.wait_for_timeout(1000)
    _click_button(app, "Habilitar todas")
    _click_button(app, "Desabilitar todas")


def _test_scrapers_interactions(app, page):
    btn = app.locator("button:has-text('Executar Health Check Completo')").first
    if btn.count() > 0:
        btn.click()
        app.wait_for_timeout(10000)


def _test_scraper_health_interactions(app, page):
    tabs = app.locator("button[data-baseweb='tab']")
    if tabs.count() > 2:
        tabs.nth(2).click()
        app.wait_for_timeout(1000)


def _test_flyers_interactions(app, page):
    _adjust_slider(app, "Últimos N dias", 14)
    _select_first_option(app, "Fonte")


def _test_config_interactions(app, page):
    tabs = app.locator("button[data-baseweb='tab']")
    for i in range(tabs.count()):
        tabs.nth(i).click()
        app.wait_for_timeout(1000)


_PAGE_ACTIONS: dict[str, callable] = {
    "precos": _test_precos_interactions,
    "historico": _test_historico_interactions,
    "promocoes": _test_promocoes_interactions,
    "ranking": _test_ranking_interactions,
    "revisao": _test_revisao_interactions,
    "calculadora": _test_calculadora_interactions,
    "diagnostico": _test_diagnostico_interactions,
    "relatorios": _test_relatorios_interactions,
    "lojas": _test_lojas_interactions,
    "ingredientes": _test_ingredientes_interactions,
    "alertas": _test_alertas_interactions,
    "scrapers": _test_scrapers_interactions,
    "scraper_health": _test_scraper_health_interactions,
    "flyers": _test_flyers_interactions,
    "config": _test_config_interactions,
}


@pytest.mark.parametrize("page_id,label", PAGES)
def test_page_with_interactions(logged_in_app_and_page, page_id, label):
    app, page = logged_in_app_and_page
    app = wake_if_sleeping(page, app)
    app.locator(f"button:has_text('{label}')").first.click()
    app.wait_for_timeout(3000)
    check_for_errors(app, f"{page_id}_loaded", page=page)

    action = _PAGE_ACTIONS.get(page_id)
    if action:
        action(app, page)
        check_for_errors(app, f"{page_id}_interaction", page=page)
    else:
        pytest.skip(f"Sem interacoes registradas para {page_id}")
