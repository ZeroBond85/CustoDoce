"""
Dashboard Page: Revisão (Review Queue)
"""

import streamlit as st

from dashboard.components.ui import inject_css
from services.config_db import add_alias_to_ingredient
from services.dashboard_queries import (
    approve_review_item_cached,
    approve_review_queue_bulk_cached,
    auto_approve_high_confidence_cached,
    get_all_ingredients,
    get_review_queue_cached,
    get_review_queue_pending_count_cached,
    reject_review_item_cached,
    reject_review_queue_bulk_cached,
)

PAGE_SIZE = 50


def render_revisao():
    inject_css()

    st.title("Fila de Revisão")
    st.markdown("*Itens com confiança < 80% aguardam validação manual*")

    # Contagem REAL de pendentes (independente da janela exibida)
    total_pending = get_review_queue_pending_count_cached()
    queue = get_review_queue_cached(limit=1000)  # janela de trabalho; paginação abaixo

    if not queue:
        st.success("Fila de revisão vazia! 🎉")
        return

    # Estatísticas (totais reais do banco + composição da janela)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Pendentes", total_pending)
    with col2:
        high_conf = sum(1 for i in queue if i.get("confidence", 0) >= 0.8)
        st.metric("Auto-aprováveis (≥80%)", high_conf)
    with col3:
        mid_conf = sum(1 for i in queue if 0.6 <= i.get("confidence", 0) < 0.8)
        st.metric("Confiança Média (60–79%)", mid_conf)

    # Auto-aprovação em lote (itens ≥80% que ficaram presos no legado)
    if high_conf:
        with st.expander(f"⚡ Auto-aprovar {high_conf} itens com confiança ≥80%", expanded=False):
            st.caption(
                "Usa o candidato #1 (top3) como ingrediente. Executa dry-run primeiro; "
                "o botão de confirmação aplica de verdade."
            )
            col_dry, col_go = st.columns(2)
            with col_dry:
                if st.button("🔍 Simular (dry-run)", key="auto_dry"):
                    stats = auto_approve_high_confidence_cached(threshold=0.80, dry_run=True)
                    st.info(
                        f"{stats['candidates']} candidatos seriam processados "
                        f"(aprovados/falhas aparecem após executar)."
                    )
            with col_go:
                if st.button("✅ Executar auto-aprovação", type="primary", key="auto_go"):
                    stats = auto_approve_high_confidence_cached(threshold=0.80, dry_run=False)
                    st.success(
                        f"✅ {stats['approved']} aprovados · ❌ {stats['failed']} falhas · "
                        f"⏭️ {stats['skipped']} sem candidato"
                    )
                    st.rerun()

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

    # Paginação server-side (renderizar milhares de itens trava o browser)
    total_pages = max(1, (len(filtered) + PAGE_SIZE - 1) // PAGE_SIZE)
    col_prev, col_page, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("◀ Anterior", key="rev_prev", disabled=st.session_state.get("rev_page", 0) == 0):
            st.session_state["rev_page"] = max(0, st.session_state.get("rev_page", 0) - 1)
            st.rerun()
    with col_page:
        st.markdown(f"**Página {st.session_state.get('rev_page', 0) + 1} de {total_pages}**")
    with col_next:
        if (
            st.button("Próxima ▶", key="rev_next")
            and st.session_state.get("rev_page", 0) < total_pages - 1
        ):
            st.session_state["rev_page"] = st.session_state.get("rev_page", 0) + 1
            st.rerun()
    page = min(st.session_state.get("rev_page", 0), total_pages - 1)
    start = page * PAGE_SIZE
    visible = filtered[start : start + PAGE_SIZE]

    # Ingredientes para seleção (necessário antes das ações em lote)
    ingredients = get_all_ingredients(include_inactive=True)
    ing_options = {i["canonical_name"]: i["id"] for i in ingredients}

    # T3.1/T3.2: bulk actions (aprovar/rejeitar em lote)
    st.markdown("**Ações em Lote**")
    col_bulk1, col_bulk2, col_bulk3 = st.columns(3)
    with col_bulk1:
        st.checkbox("Selecionar todos itens filtrados", key="bulk_select_all")
    with col_bulk2:
        bulk_ing = st.selectbox(
            "Ingrediente p/ aprovação em lote:",
            ["Selecione..."] + list(ing_options.keys()),
            key="bulk_ingredient",
        )
    with col_bulk3:
        if st.button("✅ Aprovar Selecionados", type="primary", key="bulk_approve"):
            if bulk_ing == "Selecione...":
                st.error("Selecione um ingrediente")
            else:
                selected_ids = [f["id"] for f in visible if f.get("selected")]
                if not selected_ids:
                    st.warning("Nenhum item selecionado")
                else:
                    count = approve_review_queue_bulk_cached(selected_ids, ing_options[bulk_ing])
                    st.success(f"✅ {count} itens aprovados!")
                    st.rerun()
        if st.button("❌ Rejeitar Selecionados", type="secondary", key="bulk_reject"):
            selected_ids = [f["id"] for f in visible if f.get("selected")]
            if not selected_ids:
                st.warning("Nenhum item selecionado")
            else:
                count = reject_review_queue_bulk_cached(selected_ids)
                st.success(f"❌ {count} itens rejeitados!")
                st.rerun()

    st.markdown(f"**Exibindo {len(visible)} de {len(filtered)} filtrados · {total_pending} pendentes no total**")

    # Exibir itens
    for _idx, item in enumerate(visible):
        with st.container():
            st.markdown("---")

            # Checkbox para seleção em lote
            item["selected"] = st.checkbox(
                "Selecionar", key=f"sel_{item['id']}", value=False
            )

            # Layout 2 colunas: imagem + dados
            col_img, col_data = st.columns([1, 3])

            with col_img:
                image_url = item.get("image_url") or item.get("source_url")
                if image_url:
                    try:
                        st.image(image_url, width=200, caption=f"Produto: {item.get('raw_product', 'N/A')}")
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
                    suggested = item.get("resolved_ingredient")
                    raw_product = item.get("raw_product", "")
                    if suggested and raw_product:
                        result = add_alias_to_ingredient(suggested, raw_product)
                        if result:
                            st.success(f"Alias '{raw_product}' adicionado a '{suggested}'")
                            st.rerun()
                        else:
                            st.error("Erro ao adicionar alias")
                    elif not suggested:
                        st.warning("Nenhum ingrediente sugerido para associar")
                    else:
                        st.warning("Produto original não disponível para criar alias")


__all__ = ["render_revisao"]
