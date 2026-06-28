"""
Dashboard Page: Fontes
"""

import streamlit as st
import pandas as pd
import plotly.express as px

from services.dashboard_queries import (
    get_coverage_by_ingredient,
    get_active_promotions,
    get_stores_with_frequencies,
)
from dashboard.components.ui import inject_css


def render_fontes():
    inject_css()

    st.title("Fontes de Dados")

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

        # Gráfico de cobertura
        fig = px.bar(
            df.sort_values("Lojas", ascending=True),
            x="Lojas",
            y="Ingrediente",
            orientation="h",
            title="Número de Lojas por Ingrediente",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Promoções ativas
    st.subheader("Promoções Ativas")
    promos = get_active_promotions()
    if promos:
        df = pd.DataFrame(promos)
        st.dataframe(
            df[["ingredient_id", "store_name", "raw_product", "raw_price", "raw_unit", "valid_until"]],
            use_container_width=True,
        )
    else:
        st.info("Nenhuma promoção ativa.")

    st.divider()

    # Ranking de fontes
    st.subheader("Ranking de Fontes (Lojas mais ativas)")
    stores = get_stores_with_frequencies()
    if stores:
        df = pd.DataFrame(stores)
        df = df[["name", "tier", "scraper", "is_active", "scrape_frequency"]]
        st.dataframe(df, use_container_width=True)


__all__ = ["render_fontes"]
