"""
Dashboard Page: Store Registry Review
"""

import streamlit as st

from dashboard.components.ui import inject_css
from services.dashboard_queries import (
    approve_store_registry_cached,
    get_store_registry_approved_cached,
    get_store_registry_pending_cached,
    merge_store_registry_cached,
    reject_store_registry_cached,
)
from services.dashboard_queries import get_active_stores


def render_lojas_pendentes():
    inject_css()

    st.title("Lojas Pendentes de Aprovação")
    st.markdown("*Lojas descobertas em folhetos aguardando aprovação para entrar no scraping*")

    pending = get_store_registry_pending_cached()

    if not pending:
        st.success("Nenhuma loja pendente! 🎉")
        return

    # Estatísticas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Pendentes", len(pending))
    with col2:
        with_address = sum(1 for s in pending if s.get("address"))
        st.metric("Com Endereço", with_address)
    with col3:
        matched = sum(1 for s in pending if s.get("matched_store_id"))
        st.metric("Já Casadas (auto-promoção)", matched)

    st.divider()

    for store in pending:
        with st.container():
            st.markdown("---")

            col_info, col_actions = st.columns([3, 1])

            with col_info:
                st.markdown(f"### {store['name']}")

                if store.get("matched_store_id"):
                    st.success(f"🔗 Casada com loja existente (match_score: {store.get('match_score', 0):.0%})")
                if store.get("address"):
                    st.info(f"📍 Endereço: {store['address']}")
                if store.get("region"):
                    st.caption(f"Região: {store['region']}")
                if store.get("city"):
                    st.caption(f"Cidade: {store['city']}")
                if store.get("source"):
                    st.caption(f"Descoberta via: {store['source']}")

                # Similarity info
                match_score = store.get("match_score", 0)
                if match_score:
                    st.progress(match_score, text=f"Similaridade com loja existente: {match_score:.0%}")

            with col_actions:
                st.markdown("### Ações")

                # If already matched, show approve/reject only
                if store.get("matched_store_id"):
                    if st.button("✅ Aprovar e Casar", key=f"approve_{store['id']}", type="primary"):
                        if approve_store_registry_cached(store["id"]):
                            st.success("Aprovada e casada!")
                            st.rerun()
                        else:
                            st.error("Erro ao aprovar")

                    if st.button("❌ Rejeitar", key=f"reject_{store['id']}"):
                        if reject_store_registry_cached(store["id"]):
                            st.success("Rejeitada!")
                            st.rerun()
                        else:
                            st.error("Erro ao rejeitar")

                # If not matched, offer merge or create new
                else:
                    st.caption("Loja não casada com base existente")

                    # Select target store to merge into
                    target_store = st.selectbox(
                        "Casar com loja existente:",
                        ["Selecione..."] + list(get_active_stores().keys()),
                        key=f"merge_target_{store['id']}"
                    )

                    if st.button("🔗 Casar e Aprovar", key=f"merge_{store['id']}", type="primary"):
                        if target_store == "Selecione...":
                            st.error("Selecione uma loja alvo")
                        else:
                            target_id = get_active_stores()[target_store]
                            if merge_store_registry_cached(store["id"], target_id):
                                st.success("Casada e aprovada!")
                                st.rerun()
                            else:
                                st.error("Erro ao casar")

                    if st.button("➕ Criar Nova Loja", key=f"create_{store['id']}"):
                        st.info("Funcionalidade: Criar nova loja no config + aprovar")

                    if st.button("❌ Rejeitar", key=f"reject_new_{store['id']}"):
                        if reject_store_registry_cached(store["id"]):
                            st.success("Rejeitada!")
                            st.rerun()
                        else:
                            st.error("Erro ao rejeitar")

    st.divider()

    # Approved stores
    st.subheader("✅ Lojas Aprovadas (Auto-promovidas)")
    approved = get_store_registry_approved_cached()
    if approved:
        for store in approved:
            with st.expander(f"✅ {store['name']} (promovida em {store.get('reviewed_at', store.get('promoted_at', 'N/A'))})"):
                st.caption(f"ID: {store['id']} | Match score: {store.get('match_score', 0):.0%} | Casada com: {store.get('matched_store_id', 'N/A')}")
                if store.get("address"):
                    st.caption(f"Endereço: {store['address']}")
    else:
        st.info("Nenhuma loja aprovada via auto-promoção ainda.")


__all__ = ["render_lojas_pendentes"]
