"""
Dashboard Page: Insights
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from services.dashboard_queries import (
    get_coverage_by_ingredient,
    get_latest_prices_cached,
)


def render_insights():
    st.title("Insights & Análises")

    with st.spinner("Carregando preços…"):
        prices = get_latest_prices_cached(valid_only=True, limit=5000)

    if not prices:
        st.info("Sem dados de preços disponíveis.")
        return

    st.subheader("Cobertura e Preço Médio por Ingrediente")
    coverage = get_coverage_by_ingredient()

    if coverage:
        df_cov = pd.DataFrame(coverage)
        if (
            "ingredient" not in df_cov.columns
            or "avg_ppk" not in df_cov.columns
            or df_cov["ingredient"].nunique() < 2
        ):
            st.info(
                "Heatmap requer >=2 ingredientes distintos. "
                "Aguarde maior cobertura antes de visualizar."
            )
        else:
            df_cov_sorted = df_cov.sort_values("avg_ppk", ascending=False).head(20)
            top_value = max(df_cov_sorted["avg_ppk"].max(), 1)
            fig = px.bar(
                df_cov_sorted,
                x="avg_ppk",
                y="ingredient",
                orientation="h",
                color="store_count",
                labels={
                    "avg_ppk": "R$/kg médio",
                    "ingredient": "Ingrediente",
                    "store_count": "Nº Lojas",
                },
                title="Top 20 ingredientes por R$/kg médio (cor = cobertura)",
            )
            fig.update_layout(
                yaxis={"categoryorder": "total ascending"},
                xaxis={"range": [0, top_value * 1.1]},
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
