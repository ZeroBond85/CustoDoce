"""
Dashboard Page: Ranking
"""

import streamlit as st
import pandas as pd
import plotly.express as px

from services.dashboard_queries import (
    get_longitudinal_winners_cached,
    get_price_trends_cached,
    get_cross_ingredient_ranking_cached,
    cached_get_active_ingredients,
)


def render_ranking():
    st.title("Ranking de Preços")

    tab1, tab2, tab3 = st.tabs(["Vencedores Históricos", "Tendências", "Ranking Cruzado"])

    with tab1:
        st.subheader("Lojas que mais venceram (menor R$/kg) - Últimos 90 dias")
        days = st.slider("Período (dias)", 30, 180, 90)
        with st.spinner("Calculando vencedores…"):
            winners = get_longitudinal_winners_cached(days)

        if winners:
            df = pd.DataFrame(winners)
            st.dataframe(df, use_container_width=True)

            fig = px.bar(
                df.head(20), x="ingredient", y="win_count", color="store", title="Top 20 Ingredientes por Vitórias"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados suficientes.")

    with tab2:
        st.subheader("Tendência de Preço por Ingrediente")
        ingredients = cached_get_active_ingredients()
        ing_names = [i.get("canonical_name", "") for i in ingredients if i.get("canonical_name")]

        if ing_names:
            selected = st.selectbox("Ingrediente", ing_names)
            days = st.slider("Período", 30, 180, 90, key="trend_days")

            with st.spinner("Calculando tendências…"):
                trends = get_price_trends_cached(selected, days)
            if trends:
                df = pd.DataFrame(trends)
                fig = px.line(
                    df, x="collected_at", y="price_per_kg", color="store_name", title=f"Tendência R$/kg - {selected}"
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sem dados para este ingrediente no período.")

    with tab3:
        st.subheader("Ranking Cruzado de Ingredientes")
        days = st.slider("Período (dias)", 30, 180, 90, key="cross_days")
        with st.spinner("Calculando ranking cruzado…"):
            ranking = get_cross_ingredient_ranking_cached(days)

        if ranking:
            df = pd.DataFrame(ranking)
            st.dataframe(df, use_container_width=True)

            fig = px.density_heatmap(
                df, x="store", y="ingredient", z="avg_price_per_kg", title="Heatmap R$/kg médio por Loja x Ingrediente"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados para ranking cruzado.")


__all__ = ["render_ranking"]
