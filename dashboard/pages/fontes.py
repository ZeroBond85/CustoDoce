"""
Dashboard Page: Fontes
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.components.ui import inject_css
from services.dashboard_queries import (
    _coverage_from_prices,
    _promotions_from_prices,
    get_latest_prices_cached,
    get_stores_with_frequencies,
)


def _fmt_frequency(freq: dict | str | None) -> str:
    """Converte scrape_frequency (dict) em rótulo legível."""
    if not freq or not isinstance(freq, dict):
        return "—"
    if freq.get("enabled") is False:
        return "Desativada"
    minutes = freq.get("frequency_minutes") or 0
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        cron = freq.get("cron_expression")
        return f"Cron: {cron}" if cron else "—"
    if minutes <= 60 * 25:
        return "Diária"
    if minutes <= 60 * 24 * 8:
        return "Semanal"
    if minutes <= 60 * 24 * 45:
        return "Mensal"
    return f"A cada {minutes // (60 * 24)} dias"


def render_fontes():
    inject_css()

    st.title("Fontes de Dados")

    # Uma query de preços reutilizada em cobertura + promoções.
    with st.spinner("Carregando preços…"):
        prices = get_latest_prices_cached(valid_only=True, limit=5000)

    # Cobertura por ingrediente
    st.subheader("Cobertura por Ingrediente")
    coverage = _coverage_from_prices(prices)
    if coverage:
        df = pd.DataFrame(coverage)
        df = df.rename(
            columns={
                "ingredient": "Ingrediente",
                "store_count": "Lojas",
                "prices": "Preços",
                "min_ppk": "Menor R$/kg",
                "avg_ppk": "Média R$/kg",
            }
        )
        st.dataframe(df[["Ingrediente", "Lojas", "Preços", "Menor R$/kg", "Média R$/kg"]], use_container_width=True)

        # Gráfico de cobertura
        fig = px.bar(
            df.sort_values("Lojas", ascending=True),
            x="Lojas",
            y="Ingrediente",
            orientation="h",
            title="Número de Lojas por Ingrediente",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Promoções ativas
    st.subheader("Promoções Ativas")
    promos = _promotions_from_prices(prices)
    if promos:
        df = pd.DataFrame(promos)
        st.dataframe(
            df[["ingredient_id", "store_name", "raw_product", "raw_price", "raw_unit", "valid_until"]],
            use_container_width=True,
        )
    else:
        st.info("Nenhuma promoção ativa.")

    st.divider()

    # Ranking de fontes
    st.subheader("Ranking de Fontes (Lojas mais ativas)")
    with st.spinner("Listando fontes…"):
        stores = get_stores_with_frequencies()
    if stores:
        # Nº Preços e Última Coleta por loja — do cache de preços já carregado.
        price_counts: dict = {}
        last_collect: dict = {}
        for p in prices:
            sid = p.get("store_id")
            if not sid:
                continue
            price_counts[sid] = price_counts.get(sid, 0) + 1
            ca = str(p.get("collected_at") or "")
            if ca > last_collect.get(sid, ""):
                last_collect[sid] = ca

        rows = []
        for s in stores:
            sid = s.get("id")
            rows.append(
                {
                    "Loja": s.get("name"),
                    "Tier": s.get("tier"),
                    "Scraper": s.get("scraper") or "—",
                    "Ativa": bool(s.get("active")),
                    "Frequência": _fmt_frequency(s.get("scrape_frequency")),
                    "Nº Preços": price_counts.get(sid, 0),
                    "Última Coleta": last_collect[sid][:16].replace("T", " ") if sid in last_collect else "—",
                }
            )
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Ativa": st.column_config.CheckboxColumn("Ativa?"),
            },
        )


__all__ = ["render_fontes"]
