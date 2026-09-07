"""
Dashboard Page: Anomalias de Scrapers (Fase C)

Drift temporal por loja (baseline 30d vs janela 7d) — não usa Isolation Forest.
Apresenta trend_score por loja, status e breakdown 7d vs 30d.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.components.ui import inject_css
from services.scraper_trend_detector import CRITICAL_THRESHOLD, DEGRADED_THRESHOLD, analyze_all_stores


def render_anomalias() -> None:
    inject_css()

    st.title("🔍 Anomalias de Scrapers")
    st.caption(
        "Detecção de degradação temporal: baseline 30d vs janela 7d por loja "
        f"(thresholds: degraded >{DEGRADED_THRESHOLD}, critical >{CRITICAL_THRESHOLD})."
    )

    results = analyze_all_stores()
    if not results:
        st.info("Sem dados de health disponíveis.")
        return

    df = pd.DataFrame(results)

    # KPIs
    total = len(df)
    critical = int((df["status"] == "critical").sum())
    degraded = int((df["status"] == "degraded").sum())
    normal = total - critical - degraded

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Lojas analisadas", total)
    col2.metric("🔴 Críticas", critical)
    col3.metric("🟡 Degradadas", degraded)
    col4.metric("🟢 Normais", normal)

    st.divider()

    # Tabela principal
    st.subheader("Trend Score por Loja")
    table = df.copy()
    table["status"] = table["status"].apply(
        lambda s: "🔴 Crítica" if s == "critical" else "🟡 Degradada" if s == "degraded" else "🟢 Normal"
    )
    table["baseline"] = table["baseline"].apply(lambda b: f'{b["success_rate"]:.0%} / {b["median_duration_s"]:.0f}s')
    table["current"] = table["current"].apply(lambda c: f'{c["success_rate"]:.0%} / {c["median_duration_s"]:.0f}s')
    table["trend_score"] = table["trend_score"].apply(lambda s: f"{s:.3f}")

    st.dataframe(
        table[["store_name", "trend_score", "status", "baseline", "current", "consecutive_failures"]],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    # Gráfico de barras do trend_score
    st.subheader("Distribuição de Trend Scores")
    fig = px.bar(
        df.sort_values("trend_score", ascending=False),
        x="store_name",
        y="trend_score",
        color="status",
        color_discrete_map={"critical": "#EF4444", "degraded": "#F59E0B", "normal": "#10B981"},
        labels={"store_name": "Loja", "trend_score": "Trend Score"},
        height=400,
    )
    fig.add_hline(y=DEGRADED_THRESHOLD, line_dash="dash", line_color="#F59E0B")
    fig.add_hline(y=CRITICAL_THRESHOLD, line_dash="dash", line_color="#EF4444")
    fig.update_layout(template="plotly_white")
    st.plotly_chart(fig, use_container_width=True)

    # Detalhe por loja (drill-down)
    st.divider()
    st.subheader("Detalhe por Loja")
    selected = st.selectbox("Selecionar loja", df["store_name"].tolist())
    row = df[df["store_name"] == selected].iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Trend Score", f'{row["trend_score"]:.3f}')
    c2.metric("Falhas consecutivas", int(row.get("consecutive_failures", 0)))
    c3.metric("Status", ("🔴 Crítica" if row["status"] == "critical" else "🟡 Degradada" if row["status"] == "degraded" else "🟢 Normal"))

    bl = row["baseline"]
    cu = row["current"]
    hist_df = pd.DataFrame(
        {
            "Janela": ["Baseline (30d)", "Atual (7d)"],
            "Success Rate": [bl["success_rate"], cu["success_rate"]],
            "Dur. Mediana (s)": [bl["median_duration_s"], cu["median_duration_s"]],
            "Items Mediana": [bl["median_items"], cu["median_items"]],
        }
    )
    st.dataframe(hist_df.set_index("Janela"), use_container_width=True)


__all__ = ["render_anomalias"]
