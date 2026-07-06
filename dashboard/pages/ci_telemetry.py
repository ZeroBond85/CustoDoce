"""
Dashboard page: CI Telemetry — GitHub Actions minutes consumption.

Usage:
    from dashboard.pages.ci_telemetry import render_ci_telemetry
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st


REPORT_FILE = Path(".github/minutes_report.json")


def _load_report() -> dict | None:
    """Load the CI minutes report from JSON file."""
    if not REPORT_FILE.exists():
        return None
    try:
        with REPORT_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None


def _format_minutes(minutes: float) -> str:
    """Format minutes for display."""
    if minutes < 1:
        return f"{minutes * 60:.0f}s"
    if minutes < 60:
        return f"{minutes:.1f} min"
    hours = minutes / 60
    return f"{hours:.1f} h"


def render_ci_telemetry() -> None:
    """Render the CI Telemetry page."""
    st.title("📊 CI Telemetry")
    st.caption("Monitoramento de consumo de minutos do GitHub Actions (Free Tier: 2.000 min/mês)")

    # Load report
    report = _load_report()

    if report is None:
        st.warning(
            "⚠️ Relatório não encontrado. Execute `python scripts/ci_minutes_report.py` "
            "com `GITHUB_TOKEN` configurado para gerar os dados."
        )
        st.code("GITHUB_TOKEN=<seu_token> python scripts/ci_minutes_report.py", language="bash")
        return

    # Top KPIs
    total = report.get("total_minutes", 0)
    limit = report.get("free_tier_limit", 2000)
    remaining = report.get("remaining_minutes", limit - total)
    pct_used = (total / limit * 100) if limit > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Consumido", _format_minutes(total), delta=f"{pct_used:.1f}% do limite", delta_color="inverse")
    with col2:
        st.metric("Limite Free Tier", _format_minutes(limit))
    with col3:
        st.metric("Restante", _format_minutes(max(0, remaining)), delta="⚠️ Baixo" if remaining < 200 else "OK")
    with col4:
        st.metric("Última Atualização", report.get("timestamp", "N/A")[:16].replace("T", " "))

    # Progress bar
    st.progress(min(pct_used / 100, 1.0), text=f"Uso do Free Tier: {pct_used:.1f}%")

    if remaining < 200:
        st.error(f"🚨 Atenção: Restam apenas {_format_minutes(remaining)} do free tier!")

    st.divider()

    # Workflows breakdown
    st.subheader("📋 Consumo por Workflow")
    workflows = report.get("workflows", {})
    if not workflows:
        st.info("Nenhum dado de consumo disponível.")
        return

    # Sort by minutes descending
    sorted_workflows = sorted(workflows.items(), key=lambda x: x[1], reverse=True)

    cols = st.columns([3, 2, 2, 1])
    cols[0].markdown("**Workflow**")
    cols[1].markdown("**Minutos**")
    cols[2].markdown("**% do Total**")
    cols[3].markdown("**Status**")

    for name, minutes in sorted_workflows:
        pct = (minutes / total * 100) if total > 0 else 0
        c = st.columns([3, 2, 2, 1])
        c[0].write(name)
        c[1].write(_format_minutes(minutes))
        c[2].write(f"{pct:.1f}%")
        status = "🔴 Alto" if pct > 30 else ("🟡 Médio" if pct > 10 else "🟢 Baixo")
        c[3].write(status)

    st.divider()

    # Historical trend placeholder
    st.subheader("📈 Tendência Histórica")
    st.info("📊 Gráfico de tendência será implementado com dados históricos persistidos (próxima sprint).")

    # Manual refresh button
    if st.button("🔄 Atualizar Agora", type="secondary"):
        st.rerun()
