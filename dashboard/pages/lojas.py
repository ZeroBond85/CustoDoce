"""
Dashboard Page: Lojas
"""

import streamlit as st
import pandas as pd

from services.dashboard_queries import cached_get_all_stores, cached_get_all_schedules
from services.config_db import upsert_store
from dashboard.components.ui import inject_css


def render_lojas():
    inject_css()

    st.title("Gerenciamento de Lojas")

    tabs = st.tabs(["📋 Lista", "➕ Adicionar/Editar"])

    st.info(
        "💡 A edição de YAML (stores.yaml) deve ser feita via git e commit. Use os formulários acima para alterações seguras."
    )

    with tabs[0]:  # Lista
        st.subheader("Todas as Lojas")

        include_inactive = st.checkbox("Incluir inativas", value=True)
        stores = cached_get_all_stores(include_inactive)

        if stores:
            df = pd.DataFrame(stores)
            expected_cols = ["id", "name", "tier", "scraper", "city", "active", "base_url"]
            df = df.reindex(columns=[c for c in expected_cols if c in df.columns])
            st.dataframe(df, use_container_width=True)

        st.divider()

        # Status por scrape_frequencies
        st.subheader("Status de Agendamento (scrape_frequencies)")
        schedules = cached_get_all_schedules(include_disabled=True)
        if schedules:
            df = pd.DataFrame(schedules)
            expected_cols = ["store_id", "enabled", "cron_expression", "timezone", "max_retries"]
            df = df.reindex(columns=[c for c in expected_cols if c in df.columns])
            st.dataframe(df, use_container_width=True)

    with tabs[1]:  # Adicionar/Editar
        st.subheader("Adicionar ou Editar Loja")

        stores = cached_get_all_stores(include_inactive=True)
        store_names = ["Nova Loja"] + [s["name"] for s in stores]
        selected = st.selectbox("Selecione", store_names)

        if selected != "Nova Loja":
            store = next(s for s in stores if s["name"] == selected)
            default = store
        else:
            default = {
                "id": "",
                "name": "",
                "tier": 2,
                "scraper": "website_scraper",
                "city": "Santos",
                "active": True,
                "base_url": "",
                "search_url": "",
                "selectors": {},
                "api_endpoint": "",
                "url_pattern": "",
                "publish_day": "",
            }

        with st.form("store_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Nome*", value=default["name"])
                tier = st.selectbox("Tier*", [1, 2, 3, 4], index=[1, 2, 3, 4].index(default["tier"]))
                scraper = st.selectbox(
                    "Scraper*",
                    [
                        "flyer_scraper",
                        "vtex_scraper",
                        "website_scraper",
                        "tenda_api_scraper",
                        "roldao_api_scraper",
                        "max_api_scraper",
                        "carrefour_scraper",
                        "playwright_scraper",
                        "pao_flyer_scraper",
                    ],
                    index=[
                        "flyer_scraper",
                        "vtex_scraper",
                        "website_scraper",
                        "tenda_api_scraper",
                        "roldao_api_scraper",
                        "max_api_scraper",
                        "carrefour_scraper",
                        "playwright_scraper",
                        "pao_flyer_scraper",
                    ].index(default["scraper"]),
                )
                city = st.text_input("Cidade", value=default["city"])
                active = st.checkbox("Ativa", value=default.get("active", True))

            with col2:
                base_url = st.text_input("Base URL", value=default.get("base_url", ""))
                search_url = st.text_input("Search URL", value=default.get("search_url", ""))
                api_endpoint = st.text_input("API Endpoint", value=default.get("api_endpoint", ""))
                url_pattern = st.text_input("URL Pattern (flyers)", value=default.get("url_pattern", ""))
                publish_day = st.selectbox(
                    "Dia de Publicação",
                    ["", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
                    index=["", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].index(
                        default.get("publish_day", "")
                    ),
                )

            selectors = st.text_area("Selectors (JSON)", value=str(default.get("selectors", {})).replace("'", '"'))

            submitted = st.form_submit_button("Salvar", type="primary")

            if submitted:
                try:
                    import json

                    selectors_dict = json.loads(selectors) if selectors else {}

                    store_data = {
                        "name": name,
                        "tier": tier,
                        "scraper": scraper,
                        "city": city,
                        "active": active,
                        "base_url": base_url,
                        "search_url": search_url,
                        "api_endpoint": api_endpoint,
                        "url_pattern": url_pattern,
                        "publish_day": publish_day if publish_day else None,
                        "selectors": selectors_dict,
                    }

                    if default.get("id"):
                        store_data["id"] = default["id"]

                    result = upsert_store(store_data)
                    if result:
                        st.success(f"Loja '{name}' salva com sucesso!")
                        st.rerun()
                    else:
                        st.error("Erro ao salvar loja")
                except Exception as e:
                    st.error(f"Erro: {e}")


__all__ = ["render_lojas"]
