"""
Dashboard Page: Alertas
"""

import streamlit as st
import pandas as pd

from services.dashboard_queries import (
    cached_get_all_alert_rules,
    cached_get_active_recipients,
    cached_get_all_recipients,
)
from services.config_db import upsert_alert_rule, upsert_recipient
from dashboard.components.ui import inject_css


def render_alertas():
    inject_css()

    st.title("Alertas e Regras")

    tabs = st.tabs(["📋 Regras Ativas", "➕ Nova Regra", "📨 Destinatários"])

    with tabs[0]:  # Regras
        rules = cached_get_all_alert_rules(include_disabled=True)

        if rules:
            df = pd.DataFrame(rules)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Nenhuma regra de alerta configurada.")

    with tabs[1]:  # Nova Regra
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
                ingredient = st.text_input("Ingrediente (canonical_name)", placeholder="Ex: Leite Condensado Integral")

            with col2:
                threshold = st.number_input("Limiar (R$/kg)", value=0.0, step=0.1)
                comparison = st.selectbox("Comparação", [">", "<", ">=", "<=", "=="])
                enabled = st.checkbox("Ativa", value=True)

            recipients = st.multiselect(
                "Destinatários",
                [r["email"] for r in cached_get_active_recipients("email")]
                + [r["chat_id"] for r in cached_get_active_recipients("telegram")],
            )

            submitted = st.form_submit_button("Salvar Regra", type="primary")

            if submitted:
                if not name or not trigger:
                    st.error("Nome e Gatilho são obrigatórios")
                else:
                    rule_data = {
                        "name": name,
                        "trigger": trigger,
                        "ingredient": ingredient,
                        "threshold": threshold,
                        "comparison": comparison,
                        "enabled": enabled,
                        "recipients": recipients,
                    }
                    result = upsert_alert_rule(rule_data)
                    if result:
                        st.success("Regra salva!")
                        st.rerun()
                    else:
                        st.error("Erro ao salvar")

    with tabs[2]:  # Destinatários
        st.subheader("Gerenciar Destinatários")

        recipients = cached_get_all_recipients(include_inactive=True)

        if recipients:
            df = pd.DataFrame(recipients)
            st.dataframe(df, use_container_width=True)

        st.divider()

        with st.form("recipient_form"):
            col1, col2 = st.columns(2)
            with col1:
                channel = st.selectbox("Canal", ["email", "telegram"])
                contact = st.text_input("Contato*", placeholder="email@exemplo.com ou -100xxxxxxxx")
            with col2:
                name = st.text_input("Nome", placeholder="Descrição do destinatário")
                is_active = st.checkbox("Ativo", value=True)

            submitted = st.form_submit_button("Adicionar Destinatário", type="primary")

            if submitted:
                if not contact:
                    st.error("Contato é obrigatório")
                else:
                    result = upsert_recipient(
                        {"channel": channel, "contact": contact, "name": name, "is_active": is_active}
                    )
                    if result:
                        st.success("Destinatário adicionado!")
                        st.rerun()
                    else:
                        st.error("Erro ao adicionar")


__all__ = ["render_alertas"]
