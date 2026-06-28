"""
Dashboard Page: Insights
"""

import streamlit as st
import pandas as pd
import plotly.express as px

from services.dashboard_queries import (
    get_latest_prices_cached,
    get_coverage_by_ingredient,
)


def render_insights():
    st.title("Insights & Análises")

    prices = get_latest_prices_cached(valid_only=True, limit=5000)

    if not prices:
        st.info("Sem dados de preços disponíveis.")
        return

    # Heatmap de cobertura
    st.subheader("Heatmap: Cobertura de Ingredientes x Lojas")
    coverage = get_coverage_by_ingredient()

    if coverage:
        df_cov = pd.DataFrame(coverage)
        # Create pivot for heatmap
        pivot = df_cov.pivot_table(index="ingredient", columns="store_count", values="avg_ppk", fill_value=0)

        fig = px.imshow(
            pivot.values,
            x=pivot.columns.astype(str),
            y=pivot.index,
            labels={"x": "Nº Lojas", "y": "Ingrediente", "color": "R$/kg médio"},
            title="Cobertura e Preço Médio",
            aspect="auto",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Outliers
    st.subheader("Outliers de Preço (Desvio Padrão > 2)")
    if prices:
        df = pd.DataFrame(prices)
        df["ppk"] = df.apply(lambda r: r.get("normalized", {}).get("price_per_kg", 0), axis=1)
        df = df[df["ppk"] > 0]

        # Group by ingredient
        outliers = []
        for _ing, group in df.groupby("ingredient_id"):
            mean = group["ppk"].mean()
            std = group["ppk"].std()
            if std > 0:
                group["zscore"] = (group["ppk"] - mean) / std
                out = group[group["zscore"].abs() > 2]
                if not out.empty:
                    outliers.append(out)

        if outliers:
            df_out = pd.concat(outliers)
            st.dataframe(
                df_out[["ingredient_id", "store_name", "raw_product", "ppk", "zscore"]].sort_values(
                    "zscore", key=abs, ascending=False
                ),
                use_container_width=True,
            )
        else:
            st.info("Nenhum outlier detectado.")

    st.divider()

    # Melhores ofertas
    st.subheader("Top 10 Melhores Ofertas (R$/kg)")
    if prices:
        df = pd.DataFrame(prices)
        df["ppk"] = df.apply(lambda r: r.get("normalized", {}).get("price_per_kg", 0), axis=1)
        df = df[df["ppk"] > 0].nsmallest(10, "ppk")
        st.dataframe(
            df[["ingredient_id", "store_name", "raw_product", "raw_price", "raw_unit", "ppk", "collected_at"]],
            use_container_width=True,
        )


__all__ = ["render_insights"]
