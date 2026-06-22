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
    ("relatorios", "📬", "Relatorios"),
    ("config", "⚙️", "Configuracao"),
    ("calculadora", "🧮", "Calculadora"),
    ("diagnostico", "🔬", "Diagnostico"),
]


def render_sidebar():
    with st.sidebar:
        logo_b64 = get_logo_sidebar_base64()
        if logo_b64:
            st.markdown(
                f'<div style="text-align:center;padding:0.75rem 0 0.5rem;">'
                f'<img src="data:image/png;base64,{logo_b64}" '
                f'style="width:140px;max-width:100%;height:auto;" />'
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="padding:0.75rem 0 0.5rem;text-align:center;">'
                '<h1 style="font-size:1.5rem;font-weight:800;margin:0;'
                "color:#FFF;\">CustoDoce</h1></div>",
                unsafe_allow_html=True,
            )

        st.markdown(
            '<p style="text-align:center;font-size:0.7rem;opacity:0.7;'
            'margin:0 0 1rem;font-weight:600;">'
            "Seu doce com o melhor custo</p>",
            unsafe_allow_html=True,
        )

        st.markdown("---")

        current = st.session_state.get("page", "visao_geral")

        for page_id, icon, label in PAGES:
            selected = page_id == current
            btn = st.button(
                f"{icon}  {label}",
                key=f"nav_{page_id}",
                use_container_width=True,
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
                f'<div style="text-align:center;padding:0.5rem 0;font-size:0.78rem;">'
                f"<strong>{user}</strong></div>",
                unsafe_allow_html=True,
            )
            if st.button("Sair", key="logout_btn", use_container_width=True):
                st.session_state.authenticated = False
                st.session_state.pop("token", None)
                st.session_state.pop("user", None)
                st.rerun()


def page_container(content_fn):
    content_fn()
