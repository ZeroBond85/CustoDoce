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


def _sync_query_params():
    qp = st.query_params
    if not qp:
        return
    for key, widget_key in [
        ("ingredient", "hist_ingredient"),
        ("days", "hist_days"),
        ("valid_only", "hist_valid"),
        ("chart_type", "hist_chart"),
    ]:
        if key in qp and widget_key not in st.session_state:
            val = qp[key]
            if key == "valid_only":
                val = val.lower() == "true"
            elif key == "days":
                val = int(val)
            st.session_state[widget_key] = val


def _push_query_params():
    ing = st.session_state.get("hist_ingredient", "")
    days = st.session_state.get("hist_days", 90)
    valid = st.session_state.get("hist_valid", False)
    chart = st.session_state.get("hist_chart", "Linha")
    qp = {}
    if ing:
        qp["ingredient"] = ing
    qp["days"] = str(days)
    if valid:
        qp["valid_only"] = "true"
    qp["chart_type"] = chart
    st.query_params.from_dict(qp)


def render_historico():
    inject_css()
    _sync_query_params()

    st.title("Hist\u00f3rico de Pre\u00e7os")

    ingredients = get_active_ingredients()
    ingredient_names = [i["canonical_name"] for i in ingredients]

    col1, col2 = st.columns([3, 1])
    with col1:
        selected = st.selectbox("Ingrediente", ingredient_names, key="hist_ingredient")
    with col2:
        days = st.selectbox("Per\u00edodo", [7, 15, 30, 60, 90, 180, 365], index=4, key="hist_days")

    col3, col4 = st.columns(2)
    with col3:
        valid_only = st.checkbox("Apenas pre\u00e7os v\u00e1lidos", value=False, key="hist_valid")
    with col4:
        chart_type = st.selectbox("Tipo de Gr\u00e1fico", ["Linha", "\u00c1rea", "Barras", "Dispers\u00e3o"], key="hist_chart")

    _push_query_params()

    history = get_price_history_cached(selected, days=days, valid_only=valid_only)

    if not history:
        st.info("Sem hist\u00f3rico para este ingrediente no per\u00edodo selecionado.")
        return

    df = pd.DataFrame(history)

    df["price_per_kg"] = df.apply(extract_ppk, axis=1)
    df["price_per_un"] = df.apply(extract_pun, axis=1)
    df = df[df["price_per_kg"] > 0].sort_values("collected_at")

    if df.empty:
        st.warning("Nenhum pre\u00e7o v\u00e1lido encontrado no per\u00edodo.")
        return

    st.subheader(f"Evolu\u00e7\u00e3o R$/kg - {selected} ({days} dias)")

    if chart_type == "Linha":
        fig = px.line(df, x="collected_at", y="price_per_kg", color="store_name", title="", markers=True)
    elif chart_type == "\u00c1rea":
        fig = px.area(df, x="collected_at", y="price_per_kg", color="store_name", title="")
    elif chart_type == "Barras":
        fig = px.bar(df, x="collected_at", y="price_per_kg", color="store_name", title="", barmode="group")
    else:
        fig = px.scatter(df, x="collected_at", y="price_per_kg", color="store_name", title="", hover_data=["raw_product", "raw_price", "raw_unit"])

    fig.update_layout(xaxis_title="Data", yaxis_title="R$/kg", hovermode="x unified", height=500)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Estat\u00edsticas do Per\u00edodo")

    stats_col = df.groupby("store_name")["price_per_kg"].agg(["mean", "min", "max", "std", "count"]).reset_index()
    stats_col.columns = ["Loja", "M\u00e9dia R$/kg", "M\u00ednimo", "M\u00e1ximo", "Desvio Padr\u00e3o", "N\u00ba Coletas"]
    stats_col = stats_col.sort_values("M\u00e9dia R$/kg")

    st.dataframe(stats_col, use_container_width=True)

    st.divider()
    st.subheader("Detalhamento")

    display_df = df[
        ["store_name", "raw_product", "raw_price", "raw_unit", "price_per_kg", "price_per_un", "brand", "is_promotion", "valid_until", "collected_at"]
    ].copy()
    display_df = display_df.rename(columns={
        "store_name": "Loja", "raw_product": "Produto", "raw_price": "Pre\u00e7o",
        "raw_unit": "Unid.", "price_per_kg": "R$/kg", "price_per_un": "R$/un",
        "brand": "Marca", "is_promotion": "Promoção", "valid_until": "Válido até",
        "collected_at": "Coletado em",
    })

    st.dataframe(display_df, use_container_width=True)
    st.info(f"Total: {len(df)} registros para {selected} nos \u00faltimos {days} dias")


__all__ = ["render_historico"]
