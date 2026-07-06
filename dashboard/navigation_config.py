"""
Single Source of Truth for CustoDoce Navigation.

ALL navigation constants are defined here. admin/app.py and
dashboard/components/layout.py import from this module.

Why: prevents drift when MENU_GROUPS was duplicated in 2 files and
PAGES was hardcoded in test_e2e_dashboard.py.

Usage:
    from dashboard.navigation_config import MENU_GROUPS, PAGE_FUNCTIONS
"""

from __future__ import annotations

from collections.abc import Callable

from dashboard.pages.alertas import render_alertas
from dashboard.pages.calculadora import render_calculadora
from dashboard.pages.capacity_planning import render_capacity_planning
from dashboard.pages.config import render_config
from dashboard.pages.diagnostico import render_diagnostico
from dashboard.pages.flyers import render_flyers
from dashboard.pages.fontes import render_fontes
from dashboard.pages.historico import render_historico
from dashboard.pages.ingredientes import render_ingredientes
from dashboard.pages.insights import render_insights
from dashboard.pages.lojas import render_lojas
from dashboard.pages.precos import render_precos
from dashboard.pages.promocoes import render_promocoes
from dashboard.pages.ranking import render_ranking
from dashboard.pages.relatorios import render_relatorios
from dashboard.pages.revisao import render_revisao
from dashboard.pages.scraper_health import render_scraper_health
from dashboard.pages.scrapers import render_scrapers
from dashboard.pages.ci_telemetry import render_ci_telemetry
from dashboard.pages.visao_geral import render_visao_geral

# ── PAGE_FUNCTIONS: page_id → render function ────────────────────────────────
PAGE_FUNCTIONS: dict[str, Callable] = {
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
    "capacity_planning": render_capacity_planning,
    "ci_telemetry": render_ci_telemetry,
}

# ── MENU_GROUPS: st.navigation() source of truth ──────────────────────────
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
        ("Capacidade", "📊", "capacity_planning"),
    ],
    "📦 Cadastros": [
        ("Lojas", "🏪", "lojas"),
        ("Ingredientes", "🛒", "ingredientes"),
    ],
    "🤖 Operações": [
        ("Alertas", "🔔", "alertas"),
        ("Scrapers & Logs", "🤖", "scrapers"),
        ("Scraper Health", "🏥", "scraper_health"),
        ("CI Telemetria", "📊", "ci_telemetry"),
        ("Relatórios", "📬", "relatorios"),
        ("Flyers", "📄", "flyers"),
    ],
    "🔧 Ferramentas": [
        ("Configuração", "⚙️", "config"),
        ("Diagnóstico", "🔬", "diagnostico"),
    ],
}

# ── PAGE_TITLE_ICONS: derived from MENU_GROUPS ────────────────────────────
PAGE_TITLE_ICONS: dict[str, tuple[str, str]] = {
    page_id: (label, icon) for _group_label, group_pages in MENU_GROUPS.items() for label, icon, page_id in group_pages
}

DEFAULT_PAGE = "visao_geral"

# ── PAGES: legacy sidebar (pre-st.navigation) — computed from MENU_GROUPS ─
# Format: (page_id, icon, label_without_accents)
# Used by render_legacy_sidebar() in layout.py for pre-1.36 fallback
PAGES: list[tuple[str, str, str]] = [
    (page_id, icon, label) for _group_label, group_pages in MENU_GROUPS.items() for label, icon, page_id in group_pages
]
