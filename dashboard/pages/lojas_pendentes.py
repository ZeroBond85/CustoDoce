"""
Dashboard Page: Lojas Pendentes

Review and approve/reject auto-discovered stores with address data.
"""

import pandas as pd
import streamlit as st

from dashboard.components.ui import inject_css
from services.store_registry import get_pending_review, approve_registry_entry, reject_registry_entry


def render_lojas_pendentes():
    inject_css()

    st.title("Lojas Pendentes de Revisão")

    st.info(
        "Lojas descobertas automaticamente via flyers/agregadores. "
        "Revise, aprove (mescla na tabela stores) ou rejeite."
    )

    pending = get_pending_review(limit=100)

    if not pending:
        st.success("Nenhuma loja pendente de revisão!")
    else:
        tabs = st.tabs(["🟡 Pendente", "🟢 Aprovadas", "🔴 Rejeitadas", "🔵 Mescladas"])

        with tabs[0]:
            _render_pending_tab(pending)

        with tabs[1]:
            _render_status_tab("approved", "🟢 Aprovadas")

        with tabs[2]:
            _render_status_tab("rejected", "🔴 Rejeitadas")

        with tabs[3]:
            _render_status_tab("merged", "🔵 Mescladas")


def _render_pending_tab(pending: list):
    if not pending:
        st.info("Nenhuma loja pendente.")
        return

    for entry in pending:
        with st.expander(f"{entry.name}", expanded=False):
            col1, col2 = st.columns([3, 1])

            with col1:
                st.markdown(f"**Nome:** {entry.name}")
                st.markdown(f"**Normalizado:** {entry.normalized_name}")
                st.markdown(f"**Cidade:** {entry.city or '-'}")
                st.markdown(f"**Região:** {entry.region or '-'}")
                st.markdown(f"**Tier:** {entry.tier} | **Tipo:** {entry.type} | **Origem:** {entry.source}")
                st.markdown(f"**Match Score:** {entry.match_score:.0%}" if entry.match_score else "**Match Score:** -")

                if entry.matched_store_id:
                    st.markdown(f"**Store ID (match):** {entry.matched_store_id[:12]}...")

                if entry.address:
                    st.markdown(f"**Endereço:** {entry.address}")
                if entry.neighborhood:
                    st.markdown(f"**Bairro:** {entry.neighborhood}")
                if entry.address_confidence:
                    st.markdown(f"**Confiança:** {entry.address_confidence}/10")

                st.divider()

            with col2:
                if st.button("✅ Aprovar", key=f"app_{entry.id}"):
                    try:
                        approve_registry_entry(entry.id)
                        st.success(f"{entry.name} aprovada!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Erro: {exc}")

                if st.button("❌ Rejeitar", key=f"rej_{entry.id}"):
                    try:
                        reject_registry_entry(entry.id)
                        st.success(f"{entry.name} rejeitada!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Erro: {exc}")

                if entry.address:
                    if st.button("✏️ Editar Endereço", key=f"edit_addr_{entry.id}"):
                        st.session_state[f"edit_addr_{entry.id}"] = True

                    if st.session_state.get(f"edit_addr_{entry.id}"):
                        new_addr = st.text_input("Endereço", value=entry.address, key=f"addr_input_{entry.id}")
                        if st.button("Salvar", key=f"save_addr_{entry.id}"):
                            try:
                                from services.supabase_client import get_service_client
                                client = get_service_client()
                                client.table("store_registry").update({
                                    "address": new_addr,
                                }).eq("id", entry.id).execute()
                                st.success("Endereço atualizado!")
                                st.session_state[f"edit_addr_{entry.id}"] = False
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Erro: {exc}")

    st.divider()

    st.subheader("Ação em Lote")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("[OK] Aprovar Todas", type="primary"):
            for e in pending:
                try:
                    approve_registry_entry(e.id)
                except Exception as exc:
                    st.warning(f"Erro ao aprovar {e.name}: {exc}")
            st.success(f"{len(pending)} lojas aprovadas!")
            st.rerun()

    with col2:
        if st.button("[X] Rejeitar Todas"):
            for e in pending:
                try:
                    reject_registry_entry(e.id)
                except Exception as exc:
                    st.warning(f"Erro ao rejeitar {e.name}: {exc}")
            st.success(f"{len(pending)} lojas rejeitadas!")
            st.rerun()


def _render_status_tab(status_filter: str, label: str):
    try:
        from services.supabase_client import require_service_client
        client = require_service_client()
    except Exception as exc:
        st.error(f"Sem cliente DB: {exc}")
        return

    res = (
        client.table("store_registry")
        .select("*")
        .eq("status", status_filter)
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )

    rows = res.data or []

    if not rows:
        st.info(f"Nenhuma loja {label.lower()}.")
        return

    df = pd.DataFrame([
        {
            "ID": r["id"][:8] + "...",
            "Nome": r["name"],
            "Tier": r["tier"],
            "Tipo": r["type"],
            "Cidade": r.get("city", "") or "-",
            "Endereço": r.get("address", "") or "-",
            "Região": r.get("region", "") or "-",
            "Match": f"{r.get('match_score', 0):.0%}",
            "Loja Mesclada": r.get("matched_store_id", "")[:8] + "..." if r.get("matched_store_id") else "-",
            "Revisado": (r.get("reviewed_at") or "")[:16] if r.get("reviewed_at") else "-",
        }
        for r in rows
    ])

    st.dataframe(df, use_container_width=True, hide_index=True)


__all__ = ["render_lojas_pendentes"]
