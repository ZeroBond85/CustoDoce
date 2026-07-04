"""
Dashboard Page: Configuração
"""

import streamlit as st

from dashboard.components.ui import inject_css
from services.config import get, reload as reload_config
from services.config_db import (
    get_all_alert_rules,
    get_all_feature_flags,
    get_all_recipients,
    upsert_alert_rule,
    upsert_feature_flag,
    upsert_recipient,
)


def render_config():
    inject_css()

    st.title("Configuração do Sistema")

    tabs = st.tabs(["🚩 Feature Flags", "📧 Alert Rules", "📬 Destinatários", "🔄 Recarregar Config"])

    st.info(
        "💡 As variáveis de ambiente (.env) são gerenciadas pelo Streamlit Cloud Secrets ou GitHub Actions Secrets. "
        "Edite-as diretamente nas plataformas. A edição de YAML (stores.yaml, ingredients.yaml) deve ser feita via "
        "git e commit."
    )

    with tabs[0]:  # Feature Flags
        st.subheader("Feature Flags (Liga/Desliga Funcionalidades)")
        _render_feature_flags_tab()

    with tabs[1]:  # Alert Rules
        st.subheader("Regras de Alerta")
        _render_alert_rules_tab()

    with tabs[2]:  # Recipients
        st.subheader("Destinatários de Alertas")
        _render_recipients_tab()

    with tabs[3]:  # Reload
        _render_reload_tab()


def _render_feature_flags_tab() -> None:
    """Render tab with batch form — toggle any flag, save all at once."""
    flags = get_all_feature_flags()

    if not flags:
        st.info("Nenhuma feature flag cadastrada. Use o formulário abaixo para criar a primeira.")
    else:
        with st.form("flags_batch_form", clear_on_submit=False):
            st.markdown("Edite os toggles abaixo e clique em **Salvar Tudo** para persistir todas as flags:")
            new_states: dict[str, dict] = {}
            for flag in flags:
                st.markdown(f"**{flag['key']}** — _{flag.get('description', '(sem descrição)')}_")
                enabled = st.checkbox(
                    "Ativo",
                    value=flag.get("enabled", False),
                    key=f"flag_check_{flag['key']}",
                )
                new_states[flag["key"]] = {
                    "key": flag["key"],
                    "enabled": enabled,
                    "description": flag.get("description", ""),
                }
                st.divider()

            col1, col2 = st.columns([1, 1])
            with col1:
                if st.form_submit_button("💾 Salvar Tudo", type="primary", width="stretch"):
                    failures: list[str] = []
                    for key, payload in new_states.items():
                        try:
                            upsert_feature_flag(payload)
                        except Exception as exc:  # noqa: BLE001
                            failures.append(f"{key}: {exc}")
                    if failures:
                        st.error("Falhas ao salvar:")
                        for f in failures:
                            st.write(f"- {f}")
                    else:
                        st.success(f"{len(new_states)} flag(s) atualizadas com sucesso.")
                        st.rerun()
            with col2:
                if st.form_submit_button("↩️ Reverter", width="stretch"):
                    st.rerun()

    st.divider()
    st.markdown("**Adicionar Nova Flag**")
    with st.form("new_flag"):
        key = st.text_input("Chave (ex: scraper_vtex_enabled)")
        desc = st.text_input("Descrição")
        enabled = st.checkbox("Ativo por padrão", value=False)
        if st.form_submit_button("Adicionar"):
            if not key.strip():
                st.error("Chave é obrigatória")
            elif any(f["key"] == key for f in flags):
                st.error(f"Flag '{key}' já existe. Use o toggler acima para alterar.")
            else:
                upsert_feature_flag({"key": key, "enabled": enabled, "description": desc})
                st.success("Flag adicionada!")
                st.rerun()


def _render_alert_rules_tab() -> None:
    """Render alert rules tab with batch form help + per-rule expander."""
    rules = get_all_alert_rules()

    if rules:
        st.markdown(f"Total: **{len(rules)}** regras cadastradas.")

        b1, b2 = st.columns([1, 4])
        with b1:
            enable_all = st.button("✅ Habilitar todas", key="rule_enable_all")
        with b2:
            disable_all = st.button("⛔ Desabilitar todas", key="rule_disable_all")
        if enable_all:
            for r in rules:
                upsert_alert_rule({**r, "enabled": True})
            st.success("Todas as regras habilitadas.")
            st.rerun()
        if disable_all:
            for r in rules:
                upsert_alert_rule({**r, "enabled": False})
            st.success("Todas as regras desabilitadas.")
            st.rerun()

        st.divider()

        for rule in rules:
            with (
                st.expander(f"{'✅' if rule.get('enabled') else '⛔'} {rule['name']} ({rule['trigger']})"),
                st.form(f"rule_form_{rule['id']}"),
            ):
                col1, col2 = st.columns(2)
                with col1:
                    enabled = st.checkbox(
                        "Ativo",
                        value=rule.get("enabled", True),
                        key=f"rule_en_{rule['id']}",
                    )
                    threshold = st.number_input(
                        "Threshold",
                        value=float(rule.get("threshold", 0)),
                        key=f"rule_th_{rule['id']}",
                    )
                with col2:
                    recipient_ids = rule.get("recipients", []) or []
                    st.caption(f"Destinatários: {', '.join(map(str, recipient_ids)) or 'nenhum'}")
                    st.caption(f"Criado em: {rule.get('created_at', 'N/A')}")
                if st.form_submit_button("💾 Salvar", type="primary"):
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
            if not name.strip():
                st.error("Nome é obrigatório")
            else:
                upsert_alert_rule({"name": name, "trigger": trigger, "threshold": threshold, "enabled": enabled})
                st.success("Regra criada!")
                st.rerun()


def _render_recipients_tab() -> None:
    recipients = get_all_recipients()

    if recipients:
        with st.form("recipients_batch_form"):
            st.markdown("Edite cada destinatário e clique **Salvar Tudo** para persistir.")
            new_states: dict[int, dict] = {}
            for r in recipients:
                st.markdown(f"**{r['name']}** — `{r['channel']}`: `{r.get('target', r.get('address', ''))}`")
                enabled = st.checkbox(
                    "Ativo",
                    value=r.get("enabled", True),
                    key=f"rec_en_{r['id']}",
                )
                new_states[r["id"]] = {**r, "enabled": enabled}
                st.divider()

            if st.form_submit_button("💾 Salvar Tudo", type="primary"):
                failures: list[str] = []
                for _id, payload in new_states.items():
                    try:
                        upsert_recipient(payload)
                    except Exception as exc:  # noqa: BLE001
                        failures.append(f"{payload.get('name')}: {exc}")
                if failures:
                    st.error("Falhas ao salvar:")
                    for f in failures:
                        st.write(f"- {f}")
                else:
                    st.success(f"{len(new_states)} destinatário(s) atualizados.")
                    st.rerun()

    st.divider()
    with st.form("new_recipient"):
        name = st.text_input("Nome")
        channel = st.selectbox("Canal", ["email", "telegram"])
        address = st.text_input("Endereço (email ou chat_id)")
        enabled = st.checkbox("Ativo", value=True)
        if st.form_submit_button("Adicionar"):
            if not name.strip() or not address.strip():
                st.error("Nome e endereço são obrigatórios")
            else:
                upsert_recipient({"name": name, "channel": channel, "target": address, "enabled": enabled})
                st.success("Destinatário adicionado!")
                st.rerun()


def _render_reload_tab() -> None:
    st.subheader("Recarregar Configuração")
    st.markdown("Força recarregamento de configs YAML e variáveis de ambiente.")

    if st.button("🔄 Recarregar Tudo", type="primary"):
        reload_config()
        st.success("Configuração recarregada!")
        st.rerun()

    st.divider()
    st.subheader("Config Atual (get())")
    cfg = get("features", {})
    safe_cfg = {k: v for k, v in cfg.items() if not any(s in k.upper() for s in ["PASSWORD", "SECRET", "KEY", "TOKEN"])}
    st.json(safe_cfg)


__all__ = ["render_config"]
