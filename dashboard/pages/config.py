"""
Dashboard Page: Configuração
"""

import streamlit as st
from pathlib import Path

from services.config import get, reload as reload_config
from services.config_db import (
    get_all_feature_flags,
    upsert_feature_flag,
    get_all_alert_rules,
    upsert_alert_rule,
    get_all_recipients,
    upsert_recipient,
)
from dashboard.components.ui import inject_css


def render_config():
    inject_css()

    st.title("Configuração do Sistema")

    tabs = st.tabs(
        ["🔐 Secrets (.env)", "🚩 Feature Flags", "📧 Alert Rules", "📬 Destinatários", "🔄 Recarregar Config"]
    )

    with tabs[0]:  # Secrets
        st.subheader("Variáveis de Ambiente (.env)")
        st.warning("⚠️ Alterações aqui sobrescrevem o arquivo .env. Valores sensíveis são mascarados na exibição.")

        env_path = Path(".env")
        if env_path.exists():
            with open(env_path, encoding="utf-8") as f:
                env_content = f.read()
        else:
            env_content = ""

        # Parse para exibir mascarado
        lines = env_content.strip().split("\n")
        display_lines = []
        for line in lines:
            if "=" in line and not line.strip().startswith("#"):
                key, val = line.split("=", 1)
                if any(s in key.upper() for s in ["PASSWORD", "SECRET", "KEY", "TOKEN"]):
                    val = "•" * min(len(val), 20) if val else ""
                    display_lines.append(f"{key}={val}")
                else:
                    display_lines.append(line)
            else:
                display_lines.append(line)

        edited = st.text_area("Arquivo .env", "\n".join(display_lines), height=400)

        if st.button("💾 Salvar .env", type="primary"):
            try:
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write(edited)
                st.success(".env salvo! Reinicie a aplicação para aplicar.")
            except Exception as e:
                st.error(f"Erro: {e}")

    with tabs[1]:  # Feature Flags
        st.subheader("Feature Flags (Liga/Desliga Funcionalidades)")

        flags = get_all_feature_flags()

        if flags:
            for flag in flags:
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.markdown(f"**{flag['key']}** — {flag.get('description', '')}")
                with col2:
                    new_val = st.checkbox("Ativo", value=flag.get("enabled", False), key=f"flag_{flag['key']}")
                with col3:
                    if st.button("Salvar", key=f"save_flag_{flag['key']}"):
                        upsert_feature_flag(
                            {
                                "key": flag["key"],
                                "enabled": new_val,
                                "description": flag.get("description", ""),
                            }
                        )
                        st.success(f"Flag '{flag['key']}' atualizada!")
                        st.rerun()

        st.divider()
        st.markdown("**Adicionar Nova Flag**")
        with st.form("new_flag"):
            key = st.text_input("Chave (ex: scraper_vtex_enabled)")
            desc = st.text_input("Descrição")
            enabled = st.checkbox("Ativo por padrão", value=False)
            if st.form_submit_button("Adicionar"):
                upsert_feature_flag({"key": key, "enabled": enabled, "description": desc})
                st.success("Flag adicionada!")
                st.rerun()

    with tabs[2]:  # Alert Rules
        st.subheader("Regras de Alerta")

        rules = get_all_alert_rules()

        if rules:
            for rule in rules:
                with st.expander(f"{rule['name']} ({rule['trigger']})"):
                    col1, col2 = st.columns(2)
                    with col1:
                        enabled = st.checkbox("Ativo", value=rule.get("enabled", True), key=f"rule_en_{rule['id']}")
                        threshold = st.number_input(
                            "Threshold", value=rule.get("threshold", 0), key=f"rule_th_{rule['id']}"
                        )
                    with col2:
                        if st.button("Salvar", key=f"rule_save_{rule['id']}"):
                            upsert_alert_rule({**rule, "enabled": enabled, "threshold": threshold})
                            st.success("Regra salva!")
                            st.rerun()

        st.divider()
        with st.form("new_rule"):
            name = st.text_input("Nome da Regra")
            trigger = st.selectbox("Trigger", ["price_drop", "price_spike", "new_lowest", "coverage_low"])
            threshold = st.number_input("Threshold", value=0.1)
            enabled = st.checkbox("Ativo", value=True)
            if st.form_submit_button("Criar Regra"):
                upsert_alert_rule({"name": name, "trigger": trigger, "threshold": threshold, "enabled": enabled})
                st.success("Regra criada!")
                st.rerun()

    with tabs[3]:  # Recipients
        st.subheader("Destinatários de Alertas")

        recipients = get_all_recipients()

        if recipients:
            for r in recipients:
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.markdown(f"**{r['name']}** — {r['channel']}: {r['address']}")
                with col2:
                    enabled = st.checkbox("Ativo", value=r.get("enabled", True), key=f"rec_en_{r['id']}")
                with col3:
                    if st.button("Salvar", key=f"rec_save_{r['id']}"):
                        upsert_recipient({**r, "enabled": enabled})
                        st.success("Destinatário atualizado!")
                        st.rerun()

        st.divider()
        with st.form("new_recipient"):
            name = st.text_input("Nome")
            channel = st.selectbox("Canal", ["email", "telegram"])
            address = st.text_input("Endereço (email ou chat_id)")
            enabled = st.checkbox("Ativo", value=True)
            if st.form_submit_button("Adicionar"):
                upsert_recipient({"name": name, "channel": channel, "address": address, "enabled": enabled})
                st.success("Destinatário adicionado!")
                st.rerun()

    with tabs[4]:  # Reload
        st.subheader("Recarregar Configuração")
        st.markdown("Força recarregamento de configs YAML e variáveis de ambiente.")

        if st.button("🔄 Recarregar Tudo", type="primary"):
            reload_config()
            st.success("Configuração recarregada!")
            st.rerun()

        st.divider()
        st.subheader("Config Atual (get())")
        cfg = get("features", {})
        # Show non-sensitive
        safe_cfg = {
            k: v for k, v in cfg.items() if not any(s in k.upper() for s in ["PASSWORD", "SECRET", "KEY", "TOKEN"])
        }
        st.json(safe_cfg)


__all__ = ["render_config"]
