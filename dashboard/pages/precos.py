"""
Dashboard Page: Preços
"""

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


def render_precos():
    inject_css()

    st.title("Preços")

    # Filtros
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

    # Buscar preços
    prices = get_latest_prices_cached(valid_only=True, limit=5000)

    # Filtrar
    df = pd.DataFrame(prices)
    if df.empty:
        st.info("Nenhum preço encontrado.")
        return

    df = df[df["ingredient_id"] == selected_ingredient]

    if selected_store != "Todas":
        df = df[df["store_name"] == selected_store]

    if tier_filter != "Todos":
        df = df[df["tier"] == tier_filter]

    df["price_per_kg"] = df.apply(extract_ppk, axis=1)
    df["price_per_un"] = df.apply(extract_pun, axis=1)

    # Ordenar por R$/kg
    df = df.sort_values("price_per_kg")

    # Exibir
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
            "raw_price": "Preço",
            "raw_unit": "Unidade",
            "price_per_kg": "R$/kg",
            "price_per_un": "R$/un",
            "brand": "Marca",
            "is_promotion": "Promoção",
            "valid_until": "Válido até",
            "collected_at": "Coletado em",
        },
    )

    st.info(f"Total: {len(df)} preços para {selected_ingredient}")


__all__ = ["render_precos"]
