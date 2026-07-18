"""
Dashboard Page: Lojas Pendentes

Review and approve/reject auto-discovered stores.
"""

import pandas as pd
import streamlit as st

from dashboard.components.ui import inject_css
from services.store_registry import get_pending_review


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
        return

    tabs = st.tabs(["🟡 Pendente", "🟢 Aprovadas", "🔴 Rejeitadas", "🔵 Mescladas"])

    with tabs[0]:  # Pendente
        _render_pending_tab(pending)

    with tabs[1]:  # Aprovadas
        _render_status_tab("approved", "🟢 Aprovadas")

    with tabs[2]:  # Rejeitadas
        _render_status_tab("rejected", "🔴 Rejeitadas")

    with tabs[3]:  # Mescladas
        _render_status_tab("merged", "🔵 Mescladas")


def _render_pending_tab(pending: list):
    if not pending:
        st.info("Nenhuma loja pendente.")
        return

    df = pd.DataFrame([
        {
            "ID": e.id[:8] + "...",
            "Nome": e.name,
            "Tier": e.tier,
            "Tipo": e.type,
            "Cidade": e.city or "-",
            "Origem": e.source,
            "Match": f"{e.match_score:.0%}" if e.match_score else "-",
            "Status": e.status,
        }
        for e in pending
    ])

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    st.subheader("Ação em Lote")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("[OK] Aprovar Selecionadas", type="primary"):
            _bulk_approve(pending)

    with col2:
        if st.button("[X] Rejeitar Selecionadas"):
            _bulk_reject(pending)

    with col3:
        if st.button("[S] Re-verificar Match"):
            st.info("Re-verifica similaridade com stores ativas")


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
            "Cidade": r["city"] or "-",
            "Match": f"{r.get('match_score', 0):.0%}",
            "Loja Mesclada": r.get("matched_store_id", "")[:8] + "..." if r.get("matched_store_id") else "-",
            "Revisado": r.get("reviewed_at", "")[:16] if r.get("reviewed_at") else "-",
        }
        for r in rows
    ])

    st.dataframe(df, use_container_width=True, hide_index=True)


def _bulk_approve(entries: list):
    from services.store_registry import approve_registry_entry

    for entry in entries:
        try:
            approve_registry_entry(entry.id)
        except Exception as exc:
            st.error(f"Erro ao aprovar {entry.name}: {exc}")

    st.success(f"{len(entries)} lojas aprovadas!")
    st.rerun()


def _bulk_reject(entries: list):
    from services.store_registry import reject_registry_entry

    for entry in entries:
        try:
            reject_registry_entry(entry.id)
        except Exception as exc:
            st.error(f"Erro ao rejeitar {entry.name}: {exc}")

    st.success(f"{len(entries)} lojas rejeitadas!")
    st.rerun()


__all__ = ["render_lojas_pendentes"]
