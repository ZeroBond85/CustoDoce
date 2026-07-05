"""
Dashboard Page: Promoções em Destaque
"""

from datetime import datetime, UTC

import pandas as pd
import streamlit as st

from dashboard.components.ui import inject_css
from services.price_service import get_all_current_prices


def _is_promotion(p: dict) -> bool:
    return bool(p.get("is_promotion"))


def _safe_ppk(p: dict) -> float:
    norm = p.get("normalized") if isinstance(p.get("normalized"), dict) else None
    if norm and norm.get("price_per_kg"):
        try:
            return float(norm["price_per_kg"])
        except (TypeError, ValueError):
            return 0.0
    flat = p.get("price_per_kg")
    if flat is not None:
        try:
            return float(flat)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def render_promocoes():
    inject_css()

    st.title("🏷️ Promoções em Destaque")
    st.caption(
        "Produtos com is_promotion=True ou tag de oferta. "
        "Use os filtros para encontrar a melhor oportunidade por loja ou ingrediente."
    )

    with st.spinner("Carregando promoções..."):
        prices = get_all_current_prices(valid_only=True, limit=500)

    if not prices:
        st.info("Nenhum preço recente encontrado. Configure scrapers ou aguarde a próxima coleta.")
        return

    promos_raw = [p for p in prices if _is_promotion(p)]

    if not promos_raw:
        st.info(
            "Nenhuma promoção ativa no momento. "
            "Isso é normal em períodos sem campanhas — o scraper principal continua coletando preços."
        )
        return

    df = pd.DataFrame(promos_raw)
    if "price_per_kg" not in df.columns:
        df["price_per_kg"] = [_safe_ppk(p) for p in promos_raw]
    else:
        missing_mask = df["price_per_kg"].isna()
        if missing_mask.any():
            df.loc[missing_mask, "price_per_kg"] = [
                _safe_ppk(p) for p, is_missing in zip(promos_raw, missing_mask, strict=True) if is_missing
            ]

    df = df[df["price_per_kg"] > 0].copy() if "price_per_kg" in df.columns else df.copy()

    stores = sorted({str(p.get("store_name", "N/A")) for p in promos_raw if p.get("store_name")})
    ingredients = sorted({str(p.get("ingredient_id", "N/A")) for p in promos_raw if p.get("ingredient_id")})

    st.subheader("Filtros")
    col1, col2, col3 = st.columns(3)
    with col1:
        store_filter = st.multiselect("Loja", stores, default=[])
    with col2:
        ing_filter = st.multiselect("Ingrediente", ingredients, default=[])
    with col3:
        order = st.selectbox(
            "Ordenar por",
            options=["Menor R$/kg", "Maior economia (R$/un)", "Mais recentes"],
            index=0,
        )

    filtered = df.copy()
    if store_filter and "store_name" in filtered.columns:
        filtered = filtered[filtered["store_name"].astype(str).isin(store_filter)]
    if ing_filter and "ingredient_id" in filtered.columns:
        filtered = filtered[filtered["ingredient_id"].astype(str).isin(ing_filter)]

    if order == "Menor R$/kg" and "price_per_kg" in filtered.columns:
        filtered = filtered.sort_values("price_per_kg", ascending=True)
    elif order == "Maior economia (R$/un)" and "price_per_un" in filtered.columns:
        filtered = filtered.sort_values("price_per_un", ascending=True)
    elif order == "Mais recentes" and "collected_at" in filtered.columns:
        filtered = filtered.sort_values("collected_at", ascending=False)

    st.subheader(f"Promoções ({len(filtered)} de {len(promos_raw)})")

    if filtered.empty:
        st.warning("Nenhuma promoção corresponde aos filtros. Ajuste e tente novamente.")
        return

    last_collect = ""
    if "collected_at" in df.columns and not df["collected_at"].dropna().empty:
        try:
            last_collect = str(pd.to_datetime(df["collected_at"]).max())
        except Exception:
            last_collect = str(df["collected_at"].dropna().max())

    k1, k2, k3 = st.columns(3)
    with k1:
        st.metric("Promoções ativas", len(filtered))
    with k2:
        avg_ppk = filtered["price_per_kg"].mean() if "price_per_kg" in filtered.columns else 0
        st.metric("R$/kg médio", f"R$ {avg_ppk:.2f}" if avg_ppk else "N/A")
    with k3:
        st.metric("Última coleta", last_collect[:10] if last_collect else "N/A")

    display_cols = []
    rename_map = {
        "store_name": "Loja",
        "raw_product": "Produto",
        "raw_price": "Preço (R$)",
        "raw_unit": "Unidade",
        "price_per_kg": "R$/kg",
        "price_per_un": "R$/un",
        "brand": "Marca",
        "ingredient_id": "Ingrediente",
        "collected_at": "Coletado",
    }
    for k, _label in rename_map.items():
        if k in filtered.columns:
            display_cols.append(k)
    final = filtered[display_cols].rename(columns=rename_map).reset_index(drop=True)

    st.dataframe(
        final,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Preço (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "R$/kg": st.column_config.NumberColumn(format="R$ %.2f"),
            "R$/un": st.column_config.NumberColumn(format="R$ %.2f"),
            "Coletado": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
        },
    )

    st.caption(
        f"Atualizado em {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}. "
        f"{len(promos_raw) - len(filtered)} promoções ocultadas pelos filtros."
    )


__all__ = ["render_promocoes"]
