"""
Dashboard Page: Scraper Health
Detailed health monitoring with last_run, success_rate, latency_p95, items/store.
"""

import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.ui import inject_css
from services.dashboard_queries import (
    get_recent_scraper_logs,
    get_scraper_health_dashboard,
)


def render_scraper_health():
    inject_css()

    st.title("🏥 Scraper Health Dashboard")

    health_data = get_scraper_health_dashboard()
    logs_data = get_recent_scraper_logs(100)

    col_summary = st.columns(4)
    total_stores = len(health_data)
    healthy = sum(1 for h in health_data if h.get("success_rate", 0) >= 0.95)
    degraded = sum(1 for h in health_data if 0.7 <= h.get("success_rate", 0) < 0.95)
    critical = sum(1 for h in health_data if h.get("success_rate", 0) < 0.7)

    with col_summary[0]:
        st.metric("Total Scrapers", total_stores)
    with col_summary[1]:
        st.metric("🟢 Healthy", healthy)
    with col_summary[2]:
        st.metric("🟡 Degraded", degraded)
    with col_summary[3]:
        st.metric("🔴 Critical", critical)

    st.divider()

    tabs = st.tabs(["📊 Health Overview", "📈 Latency", "📋 Raw Logs"])

    with tabs[0]:
        if health_data:
            df = pd.DataFrame(health_data)
            display_cols = [
                "store_name",
                "status_label",
                "last_run",
                "success_rate",
                "latency_p95_ms",
                "avg_items_per_run",
                "total_runs",
                "error_count",
            ]
            display_df = df[[c for c in display_cols if c in df.columns]].copy()
            display_df["success_rate"] = display_df["success_rate"].apply(lambda x: f"{x:.1%}")
            display_df["latency_p95_ms"] = display_df["latency_p95_ms"].apply(
                lambda x: f"{x / 1000:.1f}s" if x else "N/A"
            )
            display_df["avg_items_per_run"] = display_df["avg_items_per_run"].apply(lambda x: f"{x:.1f}")
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum dado de health disponível.")

    with tabs[1]:
        if health_data:
            df = pd.DataFrame(health_data)
            df_plot = df[df["latency_p95_ms"] > 0].sort_values("latency_p95_ms", ascending=False)

            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    x=df_plot["store_name"],
                    y=df_plot["latency_p95_ms"] / 1000,
                    marker_color=df_plot["success_rate"].apply(
                        lambda r: "#10B981" if r >= 0.95 else "#F59E0B" if r >= 0.7 else "#EF4444"
                    ),
                    text=df_plot["latency_p95_ms"].apply(lambda x: f"{x / 1000:.1f}s"),
                    textposition="outside",
                )
            )
            fig.update_layout(
                title="Latência P95 por Loja (segundos)",
                xaxis_title="Loja",
                yaxis_title="Latência P95 (s)",
                template="plotly_white",
                height=400,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhum dado de latência disponível.")

    with tabs[2]:
        if logs_data:
            df = pd.DataFrame(logs_data)
            # 'errors' vem como JSONB (lista em algumas linhas, nulo/scalar
            # em outras) -> pyarrow falha ao converter. Normaliza para string
            # antes do st.dataframe (Licao #51).
            if "errors" in df.columns:
                df["errors"] = df["errors"].apply(
                    lambda v: (
                        ", ".join(str(x) for x in v)
                        if isinstance(v, (list, tuple))
                        else (json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else ("" if v is None else str(v)))
                    )
                )
            cols = [
                c
                for c in ["store_name", "status", "started_at", "finished_at", "items_found", "items_matched", "errors"]
                if c in df.columns
            ]
            df = df.reindex(columns=cols)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum log disponível.")


__all__ = ["render_scraper_health"]
