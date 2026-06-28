"""
Dashboard Page: Histórico de Preços
"""

import streamlit as st
import pandas as pd
import plotly.express as px

from services.dashboard_queries import (
    get_price_history_cached,
    get_active_ingredients,
    extract_ppk,
    extract_pun,
)
from dashboard.components.ui import inject_css


def render_historico():
    inject_css()

    st.title("📈 Histórico de Preços")

    ingredients = get_active_ingredients()
    ingredient_names = [i["canonical_name"] for i in ingredients]

    col1, col2 = st.columns([3, 1])
    with col1:
        selected = st.selectbox("Ingrediente", ingredient_names, key="hist_ingredient")
    with col2:
        days = st.selectbox("Período", [7, 15, 30, 60, 90, 180, 365], index=4, key="hist_days")

    # Opções de exibição
    col3, col4 = st.columns(2)
    with col3:
        valid_only = st.checkbox("Apenas preços válidos", value=False, key="hist_valid")
    with col4:
        chart_type = st.selectbox("Tipo de Gráfico", ["Linha", "Área", "Barras", "Dispersão"], key="hist_chart")

    history = get_price_history_cached(selected, days=days, valid_only=valid_only)

    if not history:
        st.info("Sem histórico para este ingrediente no período selecionado.")
        return

    df = pd.DataFrame(history)

    df["price_per_kg"] = df.apply(extract_ppk, axis=1)
    df["price_per_un"] = df.apply(extract_pun, axis=1)
    df = df[df["price_per_kg"] > 0].sort_values("collected_at")

    if df.empty:
        st.warning("Nenhum preço válido encontrado no período.")
        return

    # Gráfico
    st.subheader(f"Evolução R$/kg - {selected} ({days} dias)")

    if chart_type == "Linha":
        fig = px.line(df, x="collected_at", y="price_per_kg", color="store_name", title="", markers=True)
    elif chart_type == "Área":
        fig = px.area(df, x="collected_at", y="price_per_kg", color="store_name", title="")
    elif chart_type == "Barras":
        fig = px.bar(df, x="collected_at", y="price_per_kg", color="store_name", title="", barmode="group")
    else:  # Dispersão
        fig = px.scatter(
            df,
            x="collected_at",
            y="price_per_kg",
            color="store_name",
            title="",
            hover_data=["raw_product", "raw_price", "raw_unit"],
        )

    fig.update_layout(
        xaxis_title="Data",
        yaxis_title="R$/kg",
        hovermode="x unified",
        height=500,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Estatísticas
    st.subheader("Estatísticas do Período")

    stats_col = df.groupby("store_name")["price_per_kg"].agg(["mean", "min", "max", "std", "count"]).reset_index()
    stats_col.columns = ["Loja", "Média R$/kg", "Mínimo", "Máximo", "Desvio Padrão", "Nº Coletas"]
    stats_col = stats_col.sort_values("Média R$/kg")

    st.dataframe(stats_col, use_container_width=True)

    st.divider()

    # Tabela detalhada
    st.subheader("Detalhamento")

    display_df = df[
        [
            "store_name",
            "raw_product",
            "raw_price",
            "raw_unit",
            "price_per_kg",
            "price_per_un",
            "brand",
            "is_promotion",
            "valid_until",
            "collected_at",
        ]
    ].copy()
    display_df = display_df.rename(
        columns={
            "store_name": "Loja",
            "raw_product": "Produto",
            "raw_price": "Preço",
            "raw_unit": "Unid.",
            "price_per_kg": "R$/kg",
            "price_per_un": "R$/un",
            "brand": "Marca",
            "is_promotion": "Promoção",
            "valid_until": "Válido até",
            "collected_at": "Coletado em",
        }
    )

    st.dataframe(display_df, use_container_width=True)

    st.info(f"Total: {len(df)} registros para {selected} nos últimos {days} dias")


__all__ = ["render_historico"]
