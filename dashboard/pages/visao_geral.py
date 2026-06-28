"""
Dashboard Page: Visão Geral
"""

import streamlit as st
import pandas as pd
import plotly.express as px

from services.dashboard_queries import (
    get_dashboard_kpis,
    get_coverage_by_ingredient,
    get_active_promotions,
    get_longitudinal_winners_cached,
    get_cross_ingredient_ranking_cached,
)
from dashboard.components.ui import info_box, inject_css


def render_visao_geral():
    inject_css()

    st.title("Visão Geral")

    # KPIs
    kpis = get_dashboard_kpis()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Preços", kpis["total_prices"])
    with col2:
        st.metric("Ingredientes Cobertos", kpis["ingredients_covered"])
    with col3:
        st.metric("Lojas Ativas", kpis["stores_active"])
    with col4:
        st.metric("Média R$/kg", f"R$ {kpis['avg_price_per_kg']:.2f}")

    st.divider()

    # Promoções ativas
    st.subheader("Promoções Ativas")
    promos = get_active_promotions()
    if promos:
        df = pd.DataFrame(promos)
        st.dataframe(
            df[["ingredient_id", "store_name", "raw_product", "raw_price", "raw_unit"]], use_container_width=True
        )
    else:
        info_box("Nenhuma promoção ativa no momento.", "info")

    st.divider()

    # Cobertura por ingrediente
    st.subheader("Cobertura por Ingrediente")
    coverage = get_coverage_by_ingredient()
    if coverage:
        df = pd.DataFrame(coverage)
        df = df.rename(
            columns={
                "ingredient": "Ingrediente",
                "store_count": "Lojas",
                "prices": "Preços",
                "min_ppk": "Menor R$/kg",
                "avg_ppk": "Média R$/kg",
            }
        )
        st.dataframe(df[["Ingrediente", "Lojas", "Preços", "Menor R$/kg", "Média R$/kg"]], use_container_width=True)

    st.divider()

    # Ranking longitudinal
    st.subheader("Lojas que mais vencem (últimos 90 dias)")
    winners = get_longitudinal_winners_cached(90)
    if winners:
        df = pd.DataFrame(winners)
        df = df.rename(
            columns={
                "ingredient_id": "Ingrediente",
                "store_name": "Loja",
                "wins": "Dias como mais barata",
            }
        )
        fig = px.bar(
            df.head(20), x="Loja", y="Dias como mais barata", color="Ingrediente", title="Top 20 Lojas por Vitórias"
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Cross-ingredient ranking
    st.subheader("Ranking Cruzado (Top 3 por ingrediente)")
    ranking = get_cross_ingredient_ranking_cached(90)
    if ranking:
        df = pd.DataFrame(ranking)
        df = df.rename(
            columns={
                "store_name": "Loja",
                "top1_count": "1º Lugar",
                "top3_count": "Top 3",
                "total_ingredients": "Total Ingredientes",
            }
        )
        st.dataframe(df, use_container_width=True)


__all__ = ["render_visao_geral"]
