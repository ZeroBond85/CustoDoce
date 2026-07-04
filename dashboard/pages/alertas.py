"""
Dashboard Page: Alertas
"""

import pandas as pd
import streamlit as st

from dashboard.components.ui import inject_css
from services.config_db import upsert_alert_rule, upsert_recipient
from services.dashboard_queries import (
    cached_get_active_recipients,
    cached_get_all_alert_rules,
    cached_get_all_recipients,
)

RULES_PAGE_SIZE = 25


def render_alertas():
    inject_css()

    st.title("Alertas e Regras")

    tabs = st.tabs(["📋 Regras", "➕ Nova Regra", "📨 Destinatários"])

    with tabs[0]:  # Regras
        _render_rules_tab()

    with tabs[1]:  # Nova Regra
        _render_new_rule_tab()

    with tabs[2]:  # Destinatários
        _render_recipients_tab()


def _render_rules_tab() -> None:
    """Render alert rules tab with pagination."""
    rules = cached_get_all_alert_rules(include_disabled=True)

    if not rules:
        st.info("Nenhuma regra de alerta configurada.")
        return

    total = len(rules)
    total_pages = max(1, (total + RULES_PAGE_SIZE - 1) // RULES_PAGE_SIZE)

    if hasattr(st, "pagination"):
        page = st.pagination(
            num_pages=total_pages,
            default=1,
            bind="query-params",
            key="alerts_page",
        )
    else:
        page = _fallback_pagination(total_pages)

    start = (page - 1) * RULES_PAGE_SIZE
    end = min(start + RULES_PAGE_SIZE, total)
    page_rules = rules[start:end]

    st.caption(f"Mostrando **{start + 1}–{end}** de **{total}** regras. Página **{page}** de **{total_pages}**.")

    b1, b2 = st.columns([1, 5])
    with b1:
        enable_all = st.button("✅ Habilitar todas", key="rule_enable_all", width="stretch")
    with b2:
        disable_all = st.button("⛔ Desabilitar todas", key="rule_disable_all", width="stretch")
    if enable_all:
        for r in rules:
            upsert_alert_rule({**r, "enabled": True})
        st.success(f"{len(rules)} regras habilitadas.")
        st.rerun()
    if disable_all:
        for r in rules:
            upsert_alert_rule({**r, "enabled": False})
        st.success(f"{len(rules)} regras desabilitadas.")
        st.rerun()

    st.divider()

    df = pd.DataFrame(page_rules)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "enabled": st.column_config.CheckboxColumn("Ativa"),
        },
    )


def _fallback_pagination(total_pages: int) -> int:
    """Manual pagination controls fallback (for Streamlit < 1.58).

    Pre-1.58 fallback. Reads page from URL query param; renders buttons to
    navigate. Returns current page on rerun.
    """
    try:
        raw = st.query_params.get("alerts_page", "1") if hasattr(st, "query_params") else "1"
        current = int(raw)
    except ValueError, TypeError, AttributeError:
        current = 1
    current = max(1, min(current, total_pages))

    cols = st.columns([1, 1, 4, 1, 1])
    nav_targets = [
        ("⏮️", "pg_first", 1, current > 1),
        ("◀️", "pg_prev", current - 1, current > 1),
        None,
        ("▶️", "pg_next", current + 1, current < total_pages),
        ("⏭️", "pg_last", total_pages, current < total_pages),
    ]
    for col, nav in zip(cols, nav_targets, strict=True):
        with col:
            if nav is None:
                st.markdown(
                    f"<div style='text-align:center;font-weight:600;'>Página {current} de {total_pages}</div>",
                    unsafe_allow_html=True,
                )
                continue
            label, key, target, can_click = nav
            if not can_click:
                st.button(label, key=key, width="stretch", disabled=True)
                continue
            if st.button(label, key=key, width="stretch") and hasattr(st, "query_params"):
                st.query_params["alerts_page"] = str(target)
                st.rerun()
    return current


def _contact_options(channel: str) -> list[str]:
    """Return contact identifiers (email or chat_id) for a given channel."""
    recipients = cached_get_active_recipients(channel) or []
    options: list[str] = []
    for r in recipients:
        target = r.get("target")
        if target:
            options.append(str(target))
    return options


def _render_new_rule_tab() -> None:
    st.subheader("Criar Nova Regra de Alerta")

    with st.form("alert_rule_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Nome da Regra*", placeholder="Ex: Preço Leite Condensado > R$ 15/kg")
            trigger = st.selectbox(
                "Gatilho*",
                [
                    "price_above_threshold",
                    "price_below_threshold",
                    "promotion_detected",
                    "new_store_price",
                    "daily_report",
                ],
            )
            ingredient = st.text_input(
                "Ingrediente (canonical_name)",
                placeholder="Ex: Leite Condensado Integral",
            )

        with col2:
            threshold = st.number_input("Limiar (R$/kg)", value=0.0, step=0.1)
            comparison = st.selectbox("Comparação", [">", "<", ">=", "<=", "=="])
            enabled = st.checkbox("Ativa", value=True)

        recipients = st.multiselect(
            "Destinatários",
            _contact_options("email") + _contact_options("telegram"),
        )

        submitted = st.form_submit_button("Salvar Regra", type="primary")

        if submitted:
            if not name or not trigger:
                st.error("Nome e Gatilho são obrigatórios")
            else:
                rule_data = {
                    "name": name,
                    "trigger": trigger,
                    "channel": "alert",
                    "condition": {
                        key: val
                        for key, val in [
                            ("ingredient", ingredient or None),
                            ("threshold", threshold if threshold > 0 else None),
                            ("comparison", comparison if threshold > 0 else None),
                        ]
                        if val is not None
                    },
                    "enabled": enabled,
                    "recipients": recipients,
                }
                result = upsert_alert_rule(rule_data)
                if result:
                    st.success("Regra salva!")
                    st.rerun()
                else:
                    st.error("Erro ao salvar")


def _render_recipients_tab() -> None:
    st.subheader("Gerenciar Destinatários")

    recipients = cached_get_all_recipients(include_inactive=True)

    if recipients:
        df = pd.DataFrame(recipients)
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    with st.form("recipient_form"):
        col1, col2 = st.columns(2)
        with col1:
            channel = st.selectbox("Canal", ["email", "telegram"])
            target = st.text_input("Contato*", placeholder="email@exemplo.com ou -100xxxxxxxx")
        with col2:
            name = st.text_input("Nome", placeholder="Descrição do destinatário")
            is_active = st.checkbox("Ativo", value=True)

        submitted = st.form_submit_button("Adicionar Destinatário", type="primary")

        if submitted:
            if not target:
                st.error("Contato é obrigatório")
            else:
                result = upsert_recipient(
                    {
                        "channel": channel,
                        "target": target,
                        "name": name,
                        "active": is_active,
                    }
                )
                if result:
                    st.success("Destinatário adicionado!")
                    st.rerun()
                else:
                    st.error("Erro ao adicionar")


__all__ = ["render_alertas"]
