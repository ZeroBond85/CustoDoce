"""
Dashboard Page: Flyers
"""

import streamlit as st
import pandas as pd

from services.dashboard_queries import get_recent_flyers_cached
from services.flyer_service import get_flyer_detail, delete_flyer
from dashboard.components.ui import inject_css


def render_flyers():
    inject_css()

    st.title("Panfletos (Flyers)")

    col1, col2 = st.columns(2)
    with col1:
        days = st.slider("Últimos N dias", 1, 60, 7)
    with col2:
        source = st.selectbox("Fonte", ["Todas", "pdf", "website", "vtex", "aggregator"])

    flyers = get_recent_flyers_cached(days, source if source != "Todas" else None)

    if not flyers:
        st.info("Nenhum flyer encontrado no período.")
        return

    # Grid de thumbnails
    st.subheader(f"Flyers ({len(flyers)} encontrados)")

    cols = st.columns(4)
    for idx, flyer in enumerate(flyers):
        with cols[idx % 4], st.container():
            if flyer.get("thumbnail_url"):
                try:
                    st.image(flyer["thumbnail_url"], use_container_width=True)
                except Exception:
                    st.caption("Erro ao carregar imagem")
            else:
                st.caption("Sem thumbnail")

            st.markdown(f"**{flyer.get('store_name', 'N/A')}**")
            st.caption(f"{flyer.get('collected_at', 'N/A')[:10]}")

            if st.button("Ver detalhes", key=f"flyer_{flyer['id']}"):
                st.session_state["selected_flyer_id"] = flyer["id"]
                st.rerun()

    # Detalhe do flyer selecionado
    if "selected_flyer_id" in st.session_state:
        flyer_id = st.session_state["selected_flyer_id"]
        detail = get_flyer_detail(flyer_id)

        if detail:
            st.divider()
            st.subheader(f"Detalhes: {detail.get('store_name', 'N/A')}")

            col1, col2 = st.columns([3, 1])
            with col1:
                if detail.get("image_url"):
                    try:
                        st.image(detail["image_url"])
                    except Exception:
                        st.caption("Erro ao carregar imagem completa")

            with col2:
                st.markdown(f"**Loja:** {detail.get('store_name')}")
                st.markdown(f"**Fonte:** {detail.get('source')}")
                st.markdown(f"**Coletado:** {detail.get('collected_at')}")
                st.markdown(f"**Itens extraídos:** {detail.get('items_count', 0)}")
                st.markdown(f"**OCR usado:** {'Sim' if detail.get('ocr_used', False) else 'Não'}")

                if st.button("Fechar", key="close_flyer"):
                    del st.session_state["selected_flyer_id"]
                    st.rerun()

                if st.button("🗑️ Excluir", key="delete_flyer"):
                    delete_flyer(flyer_id)
                    st.success("Flyer excluído")
                    del st.session_state["selected_flyer_id"]
                    st.rerun()

            # Produtos extraídos
            if detail.get("products"):
                st.subheader("Produtos Extraídos")
                df = pd.DataFrame(detail["products"])
                st.dataframe(df, use_container_width=True)


__all__ = ["render_flyers"]
