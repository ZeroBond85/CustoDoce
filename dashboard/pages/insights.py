"""
Dashboard Page: Insights
"""

import pandas as pd
import streamlit as st
from typing import Any

from services.dashboard_queries import (
    detect_outliers_cached,
    get_latest_prices_cached,
)


def _safe_ppk(r: dict[str, Any]) -> float:
    norm = r.get("normalized")
    if isinstance(norm, dict):
        try:
            return float(norm.get("price_per_kg", 0))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def render_insights() -> None:
    st.title("Insights & Análises")

    with st.spinner("Carregando preços…"):
        prices = get_latest_prices_cached(valid_only=True, limit=5000)

    if not prices:
        st.info("Sem dados de preços disponíveis.")
        return

    # Brand filter
    brands = sorted({str(p.get("brand", "Desconhecido")) for p in prices if p.get("brand")})
    brand_filter = st.multiselect("Filtrar por marca", brands, default=[], key="insights_brand_filter")
    if brand_filter:
        prices = [p for p in prices if p.get("brand") in brand_filter]

    st.divider()

    # Preços atípicos - usando RPC no banco (z-score > 2)
    st.subheader("Preços Atípicos (z-score > 2)")
    st.caption("Produtos muito acima ou abaixo da média histórica do ingrediente — podem indicar erro de coleta ou oferta real.")
    with st.spinner("Detectando outliers…"):
        outliers = detect_outliers_cached(90)

    if outliers:
        df_out = pd.DataFrame(outliers)
        st.dataframe(
            df_out[["ingredient_id", "store_name", "raw_product", "brand", "ppk", "zscore"]].sort_values(
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
            df[["ingredient_id", "store_name", "raw_product", "brand", "raw_price", "raw_unit", "ppk", "collected_at"]],
            use_container_width=True,
        )


__all__ = ["render_insights"]
