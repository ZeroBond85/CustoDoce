import streamlit as st
import pandas as pd

from services.dashboard_queries import (
    get_latest_prices_cached,
    get_active_ingredients,
    get_all_stores,
    extract_ppk,
    extract_pun,
)
from dashboard.components.ui import inject_css


def _sync_query_params():
    qp = st.query_params
    if not qp:
        return
    for key, widget_key in [("ingredient", "precos_ingredient"), ("store", "precos_store"), ("tier", "precos_tier")]:
        if key in qp and widget_key not in st.session_state:
            st.session_state[widget_key] = qp[key]


def _push_query_params():
    ing = st.session_state.get("precos_ingredient", "")
    store = st.session_state.get("precos_store", "Todas")
    tier = st.session_state.get("precos_tier", "Todos")
    qp = {}
    if ing:
        qp["ingredient"] = ing
    if store and store != "Todas":
        qp["store"] = store
    if tier and tier != "Todos":
        qp["tier"] = str(tier)
    st.query_params.from_dict(qp)


def render_precos():
    inject_css()
    _sync_query_params()

    st.title("Pre\u00e7os")

    col1, col2, col3 = st.columns(3)

    ingredients = get_active_ingredients()
    ingredient_names = [i["canonical_name"] for i in ingredients]

    with col1:
        selected_ingredient = st.selectbox("Ingrediente", ingredient_names, key="precos_ingredient")

    stores = get_all_stores(include_inactive=False)
    store_names = [s["name"] for s in stores]

    with col2:
        selected_store = st.selectbox("Loja (opcional)", ["Todas"] + store_names, key="precos_store")

    with col3:
        tier_filter = st.selectbox("Tier", ["Todos", 1, 2, 3, 4], key="precos_tier")

    _push_query_params()

    prices = get_latest_prices_cached(valid_only=True, limit=5000)

    df = pd.DataFrame(prices)
    if df.empty:
        st.info("Nenhum pre\u00e7o encontrado.")
        return

    df = df[df["ingredient_id"] == selected_ingredient]

    if selected_store != "Todas":
        df = df[df["store_name"] == selected_store]

    if tier_filter != "Todos":
        df = df[df["tier"] == tier_filter]

    df["price_per_kg"] = df.apply(extract_ppk, axis=1)
    df["price_per_un"] = df.apply(extract_pun, axis=1)
    df = df.sort_values("price_per_kg")

    st.dataframe(
        df[
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
        ],
        use_container_width=True,
        column_config={
            "store_name": "Loja",
            "raw_product": "Produto",
            "raw_price": "Pre\u00e7o",
            "raw_unit": "Unidade",
            "price_per_kg": "R$/kg",
            "price_per_un": "R$/un",
            "brand": "Marca",
            "is_promotion": "Promoção",
            "valid_until": "Válido até",
            "collected_at": "Coletado em",
        },
    )

    st.info(f"Total: {len(df)} pre\u00e7os para {selected_ingredient}")


__all__ = ["render_precos"]
