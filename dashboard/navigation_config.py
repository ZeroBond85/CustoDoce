"""
Single Source of Truth for CustoDoce Navigation.

ALL navigation constants are defined here. admin/app.py and
dashboard/components/layout.py import from this module.

Why: prevents drift when MENU_GROUPS was duplicated in 2 files and
PAGES was hardcoded in test_e2e_dashboard.py.

Usage:
    from dashboard.navigation_config import MENU_GROUPS, PAGE_TITLE_ICONS, PAGES, get_page_function
"""

from __future__ import annotations

from collections.abc import Callable

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
        ("Lojas Pendentes", "🕵️", "lojas_pendentes"),
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

# Map page_id -> module_path for lazy loading (used by admin/app.py)
# This avoids importing all page modules at startup.
_PAGE_MODULES: dict[str, str] = {
    "visao_geral": "dashboard.pages.visao_geral",
    "precos": "dashboard.pages.precos",
    "historico": "dashboard.pages.historico",
    "promocoes": "dashboard.pages.promocoes",
    "insights": "dashboard.pages.insights",
    "fontes": "dashboard.pages.fontes",
    "ranking": "dashboard.pages.ranking",
    "calculadora": "dashboard.pages.calculadora",
    "revisao": "dashboard.pages.revisao",
    "capacity_planning": "dashboard.pages.capacity_planning",
    "lojas": "dashboard.pages.lojas",
    "lojas_pendentes": "dashboard.pages.lojas_pendentes",
    "ingredientes": "dashboard.pages.ingredientes",
    "alertas": "dashboard.pages.alertas",
    "scrapers": "dashboard.pages.scrapers",
    "scraper_health": "dashboard.pages.scraper_health",
    "ci_telemetry": "dashboard.pages.ci_telemetry",
    "relatorios": "dashboard.pages.relatorios",
    "flyers": "dashboard.pages.flyers",
    "config": "dashboard.pages.config",
    "diagnostico": "dashboard.pages.diagnostico",
}


def get_page_function(page_id: str) -> Callable:
    """Lazy-load a page's render function by page_id.

    Avoids importing all page modules at startup — only loads when needed.
    Page functions are named render_<page_id> (e.g., render_visao_geral).
    """
    if page_id not in _PAGE_MODULES:
        raise KeyError(f"Unknown page_id: {page_id}")
    module_path = _PAGE_MODULES[page_id]
    module = __import__(module_path, fromlist=[f"render_{page_id}"])
    return getattr(module, f"render_{page_id}")


# ── Legacy PAGES (pre-st.navigation fallback) — computed from MENU_GROUPS ─
# Format: (page_id, icon, label_without_accents)
PAGES: list[tuple[str, str, str]] = [
    (page_id, icon, label) for _group_label, group_pages in MENU_GROUPS.items() for label, icon, page_id in group_pages
]
