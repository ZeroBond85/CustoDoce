"""
CustoDoce Dashboard - Main Application (Modular Architecture)
Refactored from 3664 lines to ~200 lines using dashboard/pages modules.

Architecture: st.navigation() (Streamlit 1.36+) with grouped sidebar.
"""

import os
import sys
from pathlib import Path

import streamlit as st

_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from dashboard.components.layout import (
    render_sidebar,
    render_skip_link,
)
from dashboard.login_page import render_login

from dashboard.pages.visao_geral import render_visao_geral
from dashboard.pages.precos import render_precos
from dashboard.pages.historico import render_historico
from dashboard.pages.flyers import render_flyers
from dashboard.pages.revisao import render_revisao
from dashboard.pages.fontes import render_fontes
from dashboard.pages.ranking import render_ranking
from dashboard.pages.insights import render_insights
from dashboard.pages.lojas import render_lojas
from dashboard.pages.ingredientes import render_ingredientes
from dashboard.pages.alertas import render_alertas
from dashboard.pages.scrapers import render_scrapers
from dashboard.pages.scraper_health import render_scraper_health
from dashboard.pages.relatorios import render_relatorios
from dashboard.pages.config import render_config
from dashboard.pages.calculadora import render_calculadora
from dashboard.pages.diagnostico import render_diagnostico
from dashboard.pages.promocoes import render_promocoes

st.set_page_config(
    page_title="CustoDoce - Painel de Preços",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Page function mapping — kept as Dict[str, Callable] for backward compat with tests.
PAGE_FUNCTIONS = {
    "visao_geral": render_visao_geral,
    "precos": render_precos,
    "historico": render_historico,
    "flyers": render_flyers,
    "revisao": render_revisao,
    "fontes": render_fontes,
    "ranking": render_ranking,
    "insights": render_insights,
    "lojas": render_lojas,
    "ingredientes": render_ingredientes,
    "alertas": render_alertas,
    "scrapers": render_scrapers,
    "scraper_health": render_scraper_health,
    "relatorios": render_relatorios,
    "config": render_config,
    "calculadora": render_calculadora,
    "diagnostico": render_diagnostico,
    "promocoes": render_promocoes,
}

# Menu grouping for st.navigation() (Streamlit 1.36+).
# Single source of truth for both legacy st.session_state.page path and the
# modern navigation API. Each tuple = (label, icon, page_id).
MENU_GROUPS: dict[str, list[tuple[str, str, str]]] = {
    "📊 Painel": [
        ("Visão Geral", "📊", "visao_geral"),
        ("Preços", "🔍", "precos"),
        ("Histórico", "📈", "historico"),
        ("Promoções", "🏷️", "promocoes"),
    ],
    "📈 Análises": [
        ("Insights", "💡", "insights"),
        ("Fontes & Ofertas", "📡", "fontes"),
        ("Ranking", "🏆", "ranking"),
        ("Calculadora", "🧮", "calculadora"),
        ("Revisão", "⚠️", "revisao"),
    ],
    "📦 Cadastros": [
        ("Lojas", "🏪", "lojas"),
        ("Ingredientes", "🛒", "ingredientes"),
    ],
    "🤖 Operações": [
        ("Alertas", "🔔", "alertas"),
        ("Scrapers & Logs", "🤖", "scrapers"),
        ("Scraper Health", "🏥", "scraper_health"),
        ("Relatórios", "📬", "relatorios"),
        ("Flyers", "📄", "flyers"),
    ],
    "🔧 Ferramentas": [
        ("Configuração", "⚙️", "config"),
        ("Diagnóstico", "🔬", "diagnostico"),
    ],
}

PAGE_TITLE_ICONS: dict[str, tuple[str, str]] = {
    page_id: (label, icon)
    for _group_label, group_pages in MENU_GROUPS.items()
    for label, icon, page_id in group_pages
}

DEFAULT_PAGE = "visao_geral"

# Password from env or generated
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    import secrets

    ADMIN_PASSWORD = secrets.token_urlsafe(16)
    os.environ.setdefault("ADMIN_PASSWORD", ADMIN_PASSWORD)


# ── Helpers (re-exported for test compatibility) ─────────────
def _flyer_status_color(status):
    colors = {"done": "#10B981", "processed": "#10B981", "pending": "#F59E0B", "failed": "#EF4444", "error": "#EF4444"}
    return colors.get(status, "#6B7280")


def _flyer_status_label(status):
    labels = {
        "done": "processado",
        "processed": "processado",
        "pending": "pendente",
        "failed": "falha",
        "error": "falha",
    }
    return labels.get(status, "unknown")


def _format_kg(normalized):
    if isinstance(normalized, dict):
        return normalized.get("price_per_kg", 0)
    return 0


def _get_kg(df):
    return df["normalized"].apply(_format_kg)


def _build_navigation():
    """Build a grouped st.navigation() from MENU_GROUPS and PAGE_FUNCTIONS.

    Returns None if Streamlit version doesn't support st.navigation() (defensive).
    Tests import PAGE_FUNCTIONS separately and don't touch the returned Page
    object — the legacy render flow runs alongside.
    """
    if not hasattr(st, "navigation") or not hasattr(st, "Page"):
        return None
    try:
        groups: dict[str, list] = {}
        for group_label, group_pages in MENU_GROUPS.items():
            group_pages_list = []
            for label, icon, page_id in group_pages:
                fn = PAGE_FUNCTIONS.get(page_id)
                if fn is None:
                    continue
                group_pages_list.append(
                    st.Page(
                        fn,
                        title=label,
                        icon=icon,
                        url_path=page_id,
                        default=(page_id == DEFAULT_PAGE),
                    )
                )
            if group_pages_list:
                groups[group_label] = group_pages_list
        if not groups:
            return None
        return st.navigation(groups)
    except Exception:
        return None


def _render_page_by_id(page_id: str) -> None:
    """Legacy fallback path: dispatch to PAGE_FUNCTIONS[page_id]()."""
    page_fn = PAGE_FUNCTIONS.get(page_id)
    if page_fn is None:
        st.error(f"Página '{page_id}' não encontrada.")
        st.session_state.page = DEFAULT_PAGE
        st.rerun()
    page_fn()


def main():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "page" not in st.session_state:
        st.session_state.page = DEFAULT_PAGE

    if not st.session_state.authenticated:
        render_login()
        st.stop()

    if hasattr(st, "navigation") and hasattr(st, "Page"):
        page_obj = _build_navigation()
        if page_obj is not None:
            render_skip_link()
            page_obj.run()
            return

    # Legacy fallback (Streamlit pre-1.36 or Page build failure)
    render_sidebar()
    render_skip_link()
    current_page = st.session_state.get("page", DEFAULT_PAGE)
    _render_page_by_id(current_page)


if __name__ == "__main__":
    main()
