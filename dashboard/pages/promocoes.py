def render_promocoes():
    import streamlit as st

    st.subheader("Promoções em Destaque")
    st.caption("Produtos com is_promotion=True ou tags de oferta.")
    import pandas as pd
    from services.price_service import get_all_current_prices

    prices = get_all_current_prices(valid_only=True, limit=500)
    promos = [p for p in prices if p.get("is_promotion") or "OFERTA" in str(p.get("ai_tags", []))]
    if not promos:
        st.info("Nenhuma promoção encontrada.")
        return
    df = pd.DataFrame(promos)
    cols = [c for c in ["store_name", "raw_product", "raw_price", "ingredient_id", "collected_at"] if c in df.columns]
    st.dataframe(df[cols], use_container_width=True)
    st.caption(f"Total: {len(promos)} promoções")
