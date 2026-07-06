"""
Dashboard Page: Revisão (Review Queue)
"""

import streamlit as st

from dashboard.components.ui import inject_css
from services.dashboard_queries import (
    approve_review_item_cached,
    get_all_ingredients,
    get_review_queue_cached,
    reject_review_item_cached,
)


def render_revisao():
    inject_css()

    st.title("Fila de Revisão")
    st.markdown("*Itens com confiança < 80% aguardam validação manual*")

    queue = get_review_queue_cached(limit=500)

    if not queue:
        st.success("Fila de revisão vazia! 🎉")
        return

    # Estatísticas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Pendentes", len(queue))
    with col2:
        high_conf = sum(1 for i in queue if i.get("confidence", 0) >= 0.6)
        st.metric("Alta Confiança (≥60%)", high_conf)
    with col3:
        low_conf = sum(1 for i in queue if i.get("confidence", 0) < 0.4)
        st.metric("Baixa Confiança (<40%)", low_conf)

    st.divider()

    # Filtros
    col1, col2 = st.columns(2)
    with col1:
        min_conf = st.slider("Confiança Mínima", 0.0, 1.0, 0.0, 0.05)
    with col2:
        match_type_filter = st.selectbox(
            "Tipo de Match", ["Todos", "exato", "proximo_nome", "proximo_apelido", "contido"]
        )

    # Filtrar
    filtered = [i for i in queue if i.get("confidence", 0) >= min_conf]
    if match_type_filter != "Todos":
        filtered = [i for i in filtered if i.get("match_type") == match_type_filter]

    if not filtered:
        st.info("Nenhum item corresponde aos filtros.")
        return

    st.markdown(f"**Exibindo {len(filtered)} de {len(queue)} itens**")

    # Ingredientes para seleção
    ingredients = get_all_ingredients(include_inactive=True)
    ing_options = {i["canonical_name"]: i["id"] for i in ingredients}

    # Exibir itens
    for _idx, item in enumerate(filtered):
        with st.container():
            st.markdown("---")

            # Layout 2 colunas: imagem + dados
            col_img, col_data = st.columns([1, 3])

            with col_img:
                image_url = item.get("image_url") or item.get("source_url")
                if image_url:
                    try:
                        st.image(image_url, width=200)
                    except Exception:
                        st.link_button("🔗 Ver Imagem/Produto", image_url)
                else:
                    st.caption("Sem imagem")

            with col_data:
                # Confiança + badge match_type
                conf = item.get("confidence", 0)
                match_type = item.get("match_type", "")

                st.progress(conf, text=f"Confiança: {conf:.0%}")

                badge_color = {"exato": "🟢", "proximo_nome": "🟡", "proximo_apelido": "🔵", "contido": "🟠"}.get(
                    match_type, "⚪"
                )
                st.markdown(f"**Tipo de Match:** {badge_color} {match_type}")

                st.markdown(f"**Produto:** {item.get('raw_product', 'N/A')}")
                st.markdown(f"**Preço:** R$ {item.get('raw_price', 0):.2f} / {item.get('raw_unit', 'N/A')}")
                st.markdown(f"**Loja:** {item.get('store_name', 'N/A')}")
                st.markdown(f"**Data:** {item.get('collected_at', 'N/A')}")

                if item.get("brand"):
                    st.markdown(f"**Marca detectada:** {item['brand']}")

            # Top 3 candidatos
            top3 = item.get("top3", [])
            if top3:
                with st.expander("📊 Top 3 Candidatos"):
                    for i, cand in enumerate(top3):
                        st.markdown(
                            f"{i + 1}. **{cand.get('canonical_name', 'N/A')}** — Score: {cand.get('score', 0):.0%} — Tipo: {cand.get('match_type', 'N/A')}"
                        )

            # Diagnóstico detalhado
            match_reason = item.get("match_reason", "")
            if match_reason:
                with st.expander("🔍 Diagnóstico do Match"):
                    st.text(match_reason)

            # Ações
            col_approve, col_reject, col_alias = st.columns(3)

            with col_approve:
                # Selectbox de ingrediente
                suggested = item.get("resolved_ingredient")
                default_idx = 0
                if suggested and suggested in ing_options:
                    default_idx = list(ing_options.keys()).index(suggested) + 1

                ing_options_with_empty = ["Selecione..."] + list(ing_options.keys())
                selected_ing = st.selectbox(
                    "Aprovar como ingrediente:", ing_options_with_empty, index=default_idx, key=f"approve_{item['id']}"
                )

                # Brand override
                detected_brand = item.get("brand", "")
                brand_options = ["Manter detecção automática"]
                if detected_brand:
                    brand_options.append(detected_brand)

                brand_override = st.selectbox("Marca:", brand_options, key=f"brand_{item['id']}")

                if st.button("✅ Aprovar", key=f"btn_approve_{item['id']}", type="primary"):
                    if selected_ing == "Selecione...":
                        st.error("Selecione um ingrediente")
                    else:
                        ing_id = ing_options[selected_ing]
                        brand_val = "" if brand_override == "Manter detecção automática" else brand_override
                        result = approve_review_item_cached(item["id"], ing_id, brand_val)
                        if result:
                            st.success("Aprovado! Item movido para preços.")
                            st.rerun()
                        else:
                            st.error("Erro ao aprovar")

            with col_reject:
                if st.button("❌ Rejeitar", key=f"btn_reject_{item['id']}"):
                    result = reject_review_item_cached(item["id"])
                    if result:
                        st.success("Rejeitado!")
                        st.rerun()
                    else:
                        st.error("Erro ao rejeitar")

            with col_alias:
                if st.button("➕ Adicionar como Alias", key=f"btn_alias_{item['id']}"):
                    # This would add the raw_product as alias to suggested ingredient
                    st.info("Funcionalidade: adicionar como alias do ingrediente sugerido")


__all__ = ["render_revisao"]
