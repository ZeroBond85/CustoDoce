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
import time

from dashboard.navigation_config import MENU_GROUPS
from .test_e2e_real import check_for_errors, wake_if_sleeping

import os
BASE_URL = os.getenv("STREAMLIT_URL", "http://localhost:8501")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

PAGES = [(page_id, label) for _group, group_pages in MENU_GROUPS.items() for label, _icon, page_id in group_pages]


def _select_first_option(page, key_substring: str):
    sel = page.locator("select").filter(has=page.locator(f"[key*='{key_substring}']")).first
    if sel.count() > 0:
        sel.select_option(index=1)
        page.wait_for_timeout(500)


def _adjust_slider(page, label_text: str, value: int):
    slider = page.locator("input[type='range']").filter(has=page.locator(f"label:has-text('{label_text}')")).first
    if slider.count() > 0 and slider.first.is_visible():
        slider.fill(str(value))
        page.wait_for_timeout(500)


def page_wait(_tabs):
    import time as _t

    _t.sleep(1200 / 1000)


def _click_first_multiselect(page, label_text: str):
    sel = page.locator("[data-testid='stMultiSelect']").filter(has=page.locator(f"label:has-text('{label_text}')")).first
    if sel.count() > 0 and sel.first.is_visible():
        sel.click()
        page.wait_for_timeout(500)
        opt = page.locator("div[role='option']").first
        if opt.count() > 0 and opt.is_visible():
            opt.click()
        page.wait_for_timeout(500)


def _click_button(page, text: str):
    btn = page.locator(f"button:has-text('{text}')").first
    if btn.count() > 0 and btn.first.is_visible():
        btn.click()
        page.wait_for_timeout(1000)


def _click_tab(tabs, index: int):
    if tabs.count() > index and tabs.nth(index).is_visible():
        tabs.nth(index).click()
        time.sleep(1.2)


def _toggle_checkbox(page, label_text: str):
    cb = page.locator("input[type='checkbox']").filter(has=page.locator(f"label:has-text('{label_text}')")).first
    if cb.count() > 0:
        cb.click()
        page.wait_for_timeout(500)


def _test_precos_interactions(page, _p):
    _select_first_option(page, "precos_ingredient")
    _select_first_option(page, "precos_store")
    _select_first_option(page, "precos_tier")


def _test_historico_interactions(page, _p):
    _select_first_option(page, "hist_ingredient")
    _adjust_slider(page, "Período", 30)
    _toggle_checkbox(page, "Apenas preços válidos")
    _select_first_option(page, "hist_chart")


def _test_promocoes_interactions(page, _p):
    _click_first_multiselect(page, "Loja")
    _click_first_multiselect(page, "Ingrediente")
    _select_first_option(page, "Ordenar por")


def _test_ranking_interactions(page, _p):
    tabs = page.locator("button[data-baseweb='tab']")
    if tabs.count() > 1:
        _click_tab(tabs, 1)
        page.wait_for_timeout(1500)
    _adjust_slider(page, "Período (dias)", 60)


def _test_revisao_interactions(page, _p):
    slider = page.locator("input[type='range']").first
    if slider.count() > 0:
        slider.fill("0.5")
        page.wait_for_timeout(1000)
    approve = page.locator("button:has-text('Aprovar')").first
    if approve.count() > 0:
        approve.click()
        confirm = page.locator("button:has-text('Sim, aprovar')").first
        if confirm.count() > 0:
            confirm.click()
            page.wait_for_timeout(2000)


def _test_calculadora_interactions(page, _p):
    select = page.locator("select, [data-testid='stSelectbox'] select").first
    if select.count() > 0:
        select.select_option(index=1)
        page.wait_for_timeout(2000)
        select.select_option(index=2)
        page.wait_for_timeout(2000)
        select.select_option(index=0)
        page.wait_for_timeout(1000)


def _test_diagnostico_interactions(page, _p):
    btn = page.locator("button:has-text('Executar Benchmarks')").first
    if btn.count() > 0:
        btn.click()
        page.wait_for_timeout(5000)


def _test_relatorios_interactions(page, _p):
    tabs = page.locator("button[data-baseweb='tab']")
    if tabs.count() > 1:
        _click_tab(tabs, 1)
        page.wait_for_timeout(1000)
    _toggle_checkbox(page, "Incluir promoções")
    _click_button(page, "Testar SMTP")
    _click_button(page, "Testar Telegram")


def _test_lojas_interactions(page, _p):
    tabs = page.locator("button[data-baseweb='tab']")
    if tabs.count() > 1:
        _click_tab(tabs, 1)
        page.wait_for_timeout(1000)


def _test_ingredientes_interactions(page, _p):
    tabs = page.locator("button[data-baseweb='tab']")
    if tabs.count() > 1:
        _click_tab(tabs, 1)
        page.wait_for_timeout(1000)
    _select_first_option(page, "Categoria")
    _click_button(page, "Testar")


def _test_alertas_interactions(page, _p):
    tabs = page.locator("button[data-baseweb='tab']")
    if tabs.count() > 1:
        _click_tab(tabs, 1)
        page.wait_for_timeout(1000)
    _click_button(page, "Habilitar todas")
    _click_button(page, "Desabilitar todas")


def _test_scrapers_interactions(page, _p):
    btn = page.locator("button:has-text('Executar Health Check Completo')").first
    if btn.count() > 0 and btn.first.is_visible():
        btn.click()
        page.wait_for_timeout(5000)


def _test_scraper_health_interactions(page, _p):
    tabs = page.locator("button[data-baseweb='tab']")
    if tabs.count() > 2:
        _click_tab(tabs, 2)
        page.wait_for_timeout(1000)


def _test_flyers_interactions(page, _p):
    _adjust_slider(page, "Últimos N dias", 14)
    _select_first_option(page, "Fonte")


def _test_config_interactions(page, _p):
    tabs = page.locator("button[data-baseweb='tab']")
    for i in range(tabs.count()):
        _click_tab(tabs, i)
        page.wait_for_timeout(1000)


_PAGE_ACTIONS: dict = {
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
    "visao_geral": lambda *_: None,
    "capacity_planning": lambda *_: None,
    "ci_telemetry": lambda *_: None,
    "insights": lambda *_: None,
    "fontes": lambda *_: None,
}


def _navigate_to_page(page, app, label: str) -> bool:
    """Navega para pagina via sidebar, testa em app (cloud) e page (local)."""
    containers = [c for c in (app, page) if c is not None]
    for container in containers:
        sidebar = container.locator('[data-testid="stSidebar"]')
        if sidebar.count() > 0:
            link = sidebar.locator("a").filter(has_text=label).first
            if link.count() > 0:
                link.click()
                page.wait_for_timeout(1500)
                return True
        btn = container.locator(f"button:has-text('{label}')").first
        if btn.count() > 0:
            btn.click()
            page.wait_for_timeout(1500)
            return True
    return False


@pytest.mark.parametrize("page_id,label", PAGES)
def test_page_with_interactions(logged_in_app_and_page_local, page_id, label):
    app, page = logged_in_app_and_page_local
    page = wake_if_sleeping(page, app)
    if not _navigate_to_page(page, app, label):
        import os as _os

        report_dir = _os.path.join("data", "regression_screenshots")
        _os.makedirs(report_dir, exist_ok=True)
        ts = _os.urandom(4).hex()
        with open(_os.path.join(report_dir, f"missing_{page_id}_{ts}.png"), "wb") as f:
            f.write(page.screenshot())
        pytest.fail(
            f"Nav link/botao '{label}' nao encontrado na sidebar. "
            f"Screenshot: data/regression_screenshots/missing_{page_id}_{ts}.png"
        )
    page.wait_for_timeout(1500)
    check_for_errors(page, f"{page_id}_loaded", page=page)

    action = _PAGE_ACTIONS.get(page_id)
    if action:
        action(page, page)
        check_for_errors(page, f"{page_id}_interaction", page=page)
    # Pagina sem interacoes registradas: navegou + sem erro = sucesso (nao skip).
