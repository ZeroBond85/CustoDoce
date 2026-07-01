import streamlit as st
from dashboard.components.ui import get_logo_sidebar_base64

PAGES = [
    ("visao_geral", "📊", "Visao Geral"),
    ("precos", "🔍", "Precos"),
    ("historico", "📈", "Historico"),
    ("flyers", "📄", "Flyers"),
    ("revisao", "⚠️", "Revisao"),
    ("fontes", "📡", "Fontes & Ofertas"),
    ("ranking", "🏆", "Ranking"),
    ("insights", "💡", "Insights"),
    ("lojas", "🏪", "Lojas"),
    ("ingredientes", "🛒", "Ingredientes"),
    ("alertas", "🔔", "Alertas"),
    ("scrapers", "🤖", "Scrapers & Logs"),
    ("scraper_health", "🏥", "Scraper Health"),
    ("relatorios", "📬", "Relatorios"),
    ("config", "⚙️", "Configuracao"),
    ("calculadora", "🧮", "Calculadora"),
    ("diagnostico", "🔬", "Diagnostico"),
    ("promocoes", "🏷️", "Promocoes"),
    ("capacity_planning", "📊", "Capacidade"),
]

# Sidebar groups — same single-source-of-truth shape as admin/app.py::MENU_GROUPS
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
        ("Relatórios", "📬", "relatorios"),
        ("Flyers", "📄", "flyers"),
    ],
    "🔧 Ferramentas": [
        ("Configuração", "⚙️", "config"),
        ("Diagnóstico", "🔬", "diagnostico"),
    ],
}

DEFAULT_PAGE = "visao_geral"


def render_legacy_sidebar():
    """Fallback sidebar using manual buttons (pre-1.36 Streamlit)."""
    with st.sidebar:
        logo_b64 = get_logo_sidebar_base64()
        if logo_b64:
            st.markdown(
                f'<div style="text-align:center;padding:0.75rem 0 0.5rem;">'
                f'<img src="data:image/png;base64,{logo_b64}" '
                f'style="width:220px;max-width:100%;height:auto;" />'
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="padding:0.75rem 0 0.5rem;text-align:center;">'
                '<h1 style="font-size:1.5rem;font-weight:800;margin:0;'
                'color:#FFF;">CustoDoce</h1></div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<p style="text-align:center;font-size:0.9rem;opacity:0.75;'
            'margin:0 0 1rem;font-weight:600;">'
            "Seu doce com o melhor custo</p>",
            unsafe_allow_html=True,
        )

        st.markdown("---")

        current = st.session_state.get("page", DEFAULT_PAGE)

        for page_id, icon, label in PAGES:
            selected = page_id == current
            btn = st.button(
                f"{icon}  {label}",
                key=f"nav_{page_id}",
                width="stretch",
                type="primary" if selected else "secondary",
                help=f"Ir para {label}",
            )
            if btn:
                st.session_state.page = page_id
                st.rerun()

        st.markdown("---")

        auth = st.session_state.get("authenticated", False)
        user = st.session_state.get("user", "admin")
        if auth:
            st.markdown(
                f'<div style="text-align:center;padding:0.5rem 0;font-size:0.78rem;"><strong>{user}</strong></div>',
                unsafe_allow_html=True,
            )
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("Limpar Cache", key="clear_cache_btn", width="stretch"):
                    st.cache_data.clear()
                    st.rerun()
            with col2:
                if st.button("Sair", key="logout_btn", width="stretch"):
                    st.session_state.authenticated = False
                    st.session_state.pop("token", None)
                    st.session_state.pop("user", None)
                    st.rerun()


def render_sidebar():
    """Sidebar renderer.

    Streamlit 1.36+: native `st.navigation()` owns the sidebar content, so the
    legacy button loop is no longer needed. The admin/app.py main() detects
    Streamlit version and uses st.navigation() when available — render_sidebar
    becomes a thin wrapper that only renders the footer (logout / clear cache)
    inside an expander.

    Pre-1.36: falls back to render_legacy_sidebar() with the original button
    loop plus footer controls.
    """
    if hasattr(st, "navigation") and hasattr(st, "Page"):
        _render_nav_footer()
        return
    render_legacy_sidebar()


def _render_nav_footer():
    """Logout / clear cache controls appended below st.navigation() sidebar."""
    auth = st.session_state.get("authenticated", False)
    if not auth:
        return
    user = st.session_state.get("user", "admin")
    with st.sidebar:
        st.markdown("---")
        st.markdown(
            f'<div style="text-align:center;padding:0.5rem 0;font-size:0.78rem;"><strong>{user}</strong></div>',
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Limpar Cache", key="clear_cache_btn", width="stretch"):
                st.cache_data.clear()
                st.rerun()
        with col2:
            if st.button("Sair", key="logout_btn", width="stretch"):
                st.session_state.authenticated = False
                st.session_state.pop("token", None)
                st.session_state.pop("user", None)
                st.rerun()


def render_skip_link():
    st.markdown(
        '<a href="#main-content" class="skip-link" tabindex="1">Pular para conteúdo</a>'
        '<div id="main-content"></div>',
        unsafe_allow_html=True,
    )


def page_container(content_fn):
    render_skip_link()
    content_fn()
