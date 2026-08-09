"""
Dashboard Page: Insights
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from services.dashboard_queries import (
    _coverage_from_prices,
    detect_outliers_cached,
    get_latest_prices_cached,
)


def _safe_ppk(r: dict) -> float:
    norm = r.get("normalized")
    if isinstance(norm, dict):
        try:
            return float(norm.get("price_per_kg", 0))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def render_insights():
    st.title("Insights & Análises")

    with st.spinner("Carregando preços…"):
        prices = get_latest_prices_cached(valid_only=True, limit=5000)

    if not prices:
        st.info("Sem dados de preços disponíveis.")
        return

    st.subheader("Cobertura e Preço Médio por Ingrediente")
    # Reutiliza os preços já carregados acima — evita 2ª query de 5000 rows.
    coverage = _coverage_from_prices(prices)

    if coverage:
        df_cov = pd.DataFrame(coverage)
        if "ingredient" not in df_cov.columns or "avg_ppk" not in df_cov.columns or df_cov["ingredient"].nunique() < 2:
            st.info("Heatmap requer >=2 ingredientes distintos. Aguarde maior cobertura antes de visualizar.")
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

    # Outliers - usando RPC no banco (z-score > 2)
    st.subheader("Outliers de Preço (Desvio Padrão > 2)")
    with st.spinner("Detectando outliers…"):
        outliers = detect_outliers_cached(90)

    if outliers:
        df_out = pd.DataFrame(outliers)
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
        df["ppk"] = df.apply(_safe_ppk, axis=1)
        df = df[df["ppk"] > 0].nsmallest(10, "ppk")
        st.dataframe(
            df[["ingredient_id", "store_name", "raw_product", "raw_price", "raw_unit", "ppk", "collected_at"]],
            use_container_width=True,
        )


__all__ = ["render_insights"]
