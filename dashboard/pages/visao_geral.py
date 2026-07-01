"""
Dashboard Page: Visão Geral
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.components.ui import info_box, inject_css
from services.dashboard_queries import (
    get_active_promotions,
    get_coverage_by_ingredient,
    get_cross_ingredient_ranking_cached,
    get_dashboard_kpis,
    get_longitudinal_winners_cached,
)


def render_visao_geral():
    inject_css()

    st.title("Visão Geral")

    kpis = get_dashboard_kpis()

    # Sprint 8: KPI row uses .cd-kpi-row class for mobile responsiveness
    # (1 column @ ≤640px, 2 cols @ ≤768px, 4 cols on desktop).
    st.markdown('<div class="cd-kpi-row">', unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4, gap="small")
    with k1:
        st.metric("Total Preços", kpis["total_prices"])
    with k2:
        st.metric("Ingredientes Cobertos", kpis["ingredients_covered"])
    with k3:
        st.metric("Lojas Ativas", kpis["stores_active"])
    with k4:
        st.metric("Média R$/kg", f"R$ {kpis['avg_price_per_kg']:.2f}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    # Promoções ativas
    st.subheader("Promoções Ativas")
    with st.spinner("Buscando promoções ativas…"):
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
    with st.spinner("Calculando cobertura…"):
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
    with st.spinner("Calculando vencedores longitudinais…"):
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
    with st.spinner("Calculando ranking cruzado…"):
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
