"""
Dashboard Page: Scrapers
"""

import json
import pandas as pd
import streamlit as st

from dashboard.components.ui import inject_css
from services.dashboard_queries import (
    get_recent_scraper_logs,
    get_store_health,
    get_stores_with_frequencies,
)


def _sanitize_df_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Converte colunas object que contenham listas/dicts (JSONB do
    Supabase) para string, evitando pyarrow ArrowInvalid no
    st.dataframe ('cannot mix list and non-list'). Licao #51.
    """
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(
                lambda v: (
                    ", ".join(str(x) for x in v)
                    if isinstance(v, (list, tuple))
                    else (json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else ("" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)))
                )
            )
    return df


def render_scrapers():
    inject_css()

    st.title("Scrapers & Coleta")

    tabs = st.tabs(["📊 Status & Logs", "⚙️ Agendamentos", "🏥 Health Check"])

    with tabs[0]:  # Status & Logs
        st.subheader("Logs Recentes de Coleta")

        logs = get_recent_scraper_logs(100)
        if logs:
            df = pd.DataFrame(logs)
            # Colunas JSONB (ex.: 'errors') vem como lista em algumas linhas e
            # nulo/scalar em outras -> pyarrow falha (ArrowInvalid: cannot mix
            # list and non-list). Normaliza TODAS as colunas object que
            # contenham listas/dicts para string antes do st.dataframe (Licao #51).
            df = _sanitize_df_for_display(df)
            cols = [
                c
                for c in ["store_name", "status", "started_at", "finished_at", "items_found", "items_matched", "errors"]
                if c in df.columns
            ]
            df = df.reindex(columns=cols)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Nenhum log encontrado.")

        st.divider()

        # Health check por loja
        st.subheader("Saúde das Lojas (últimas 200 execuções)")
        health = get_store_health()
        if health:
            df = pd.DataFrame(health)
            if "errors" in df.columns and "runs" in df.columns:
                df["error_rate"] = df["errors"] / df["runs"].replace(0, 1)
                df = df.sort_values("error_rate", ascending=False)
            df = _sanitize_df_for_display(df)
            st.dataframe(df, use_container_width=True)

    with tabs[1]:  # Agendamentos
        st.subheader("Agendamentos de Coleta (scrape_frequencies)")

        stores = get_stores_with_frequencies()

        if not stores:
            st.info("Nenhuma loja configurada.")
            return

        # Tabela editável de agendamentos
        freq_data = []
        for s in stores:
            freq = s.get("scrape_frequency")
            freq_data.append(
                {
                    "Loja": s["name"],
                    "Tier": s["tier"],
                    "Scraper": s["scraper"],
                    "Ativa": s.get("active", False),
                    "Agendado": freq.get("enabled", False) if freq else False,
                    "Cron": freq.get("cron_expression", "") if freq else "",
                    "Timezone": freq.get("timezone", "") if freq else "",
                    "Max Retries": freq.get("max_retries", 0) if freq else 0,
                }
            )

        df = pd.DataFrame(freq_data)
        st.dataframe(df, use_container_width=True)

        st.info("""
        **Cron Expressions Comuns:**
        - `0 6 * * 2,4` — Quarta e Sexta às 06:00 (flyers semanais)
        - `0 6 * * *` — Diário às 06:00 (VTEX)
        - `0 6 * * 0` — Domingo às 06:00 (semanal)
        - `0 6 1 * *` — Dia 1 de cada mês às 06:00
        """)

    with tabs[2]:  # Health Check
        st.subheader("Health Check Manual")

        if st.button("🔍 Executar Health Check Completo"):
            from scripts.store_health_check import main as health_check_main

            with st.spinner("Testando lojas desativadas..."):
                results = health_check_main()
                st.json(results)


__all__ = ["render_scrapers"]
