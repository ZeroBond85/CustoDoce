"""
CustoDoce Dashboard - Main Application (Modular Architecture)
Refactored from 3664 lines to ~200 lines using dashboard/pages modules.
"""

import os
import sys
from pathlib import Path

import streamlit as st

# Ensure repo root is in sys.path
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from dashboard.components.layout import render_sidebar
from dashboard.login_page import render_login

# Import all page render functions
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

st.set_page_config(
    page_title="CustoDoce - Painel de Preços",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Page function mapping
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
}

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


def main():
    # Initialize session state
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "page" not in st.session_state:
        st.session_state.page = "visao_geral"

    # Authentication
    if not st.session_state.authenticated:
        render_login()
        return

    # Render sidebar navigation
    render_sidebar()

    # Get current page
    current_page = st.session_state.get("page", "visao_geral")

    # Execute page function
    page_fn = PAGE_FUNCTIONS.get(current_page)
    if page_fn:
        page_fn()
    else:
        st.error(f"Página '{current_page}' não encontrada.")
        st.session_state.page = "visao_geral"
        st.rerun()


if __name__ == "__main__":
    main()
