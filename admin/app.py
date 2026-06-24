import html
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import yaml
import json
import re
import shutil
import httpx
import statistics
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.auth import (
    generate_totp_secret as _gen_totp,
    get_totp_uri as _get_totp_uri,
    hash_password as _hash_pw,
    verify_totp as _verify_totp,
)
from services.config import get as get_config, reload as reload_config
from services.price_service import (
    approve_review_item,
    get_all_current_prices,
    get_latest_prices,
    get_price_history,
    get_review_queue,
    get_longitudinal_winners,
    get_price_trends,
    get_cross_ingredient_ranking,
    get_cheapest_prices,
    reject_review_item,
    search_prices,
)
from services.supabase_client import get_service_client
from services.config_db import (
    get_all_ingredients,
    get_active_ingredients,
    upsert_ingredient,
    delete_ingredient,
    get_all_stores,
    upsert_store,
    delete_store,
    get_all_schedules,
    upsert_schedule,
    delete_schedule,
    get_scrape_frequency,
    upsert_scrape_frequency,
    get_active_recipients,
    get_all_recipients,
    upsert_recipient,
    delete_recipient,
    get_all_alert_rules,
    upsert_alert_rule,
)
from dashboard.components.layout import render_sidebar
from dashboard.components.ui import (
    info_box,
    inject_css,
    plotly_theme,
    section_title,
)
from dashboard.login_page import render_login

# Ensure repo root is in sys.path (needed by Streamlit Cloud)
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

load_dotenv()
if not os.environ.get("ADMIN_PASSWORD"):
    import secrets
    generated = secrets.token_urlsafe(16)
    os.environ.setdefault("ADMIN_PASSWORD", generated)

st.set_page_config(
    page_title="CustoDoce - Painel de Precos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

INGREDIENTS_FILE = "config/ingredients.yaml"
CD_ORANGE = "#F59E42"
CD_PINK = "#E8739A"
CD_BLUE = "#3B7DD8"

_COL_PT = {
    "store_name": "Loja", "ingredient_id": "Ingrediente", "raw_product": "Produto",
    "raw_price": "Preco Bruto (R$)", "raw_unit": "Unidade", "tier": "Tier",
    "is_promotion": "Promocao", "valid_until": "Valido Ate", "confidence": "Confianca",
    "collected_at": "Coletado Em", "brand": "Marca", "price_per_kg": "R$/kg",
    "price_per_un": "R$/un", "active": "Ativo", "channel": "Canal",
    "target": "Destino", "name": "Nome", "trigger": "Gatilho",
    "frequency_minutes": "Frequencia (min)", "enabled": "Ativo",
    "canonical_name": "Nome", "category": "Categoria", "aliases": "Aliases",
    "unit_target": "Unidade Alvo", "status": "Status", "items_found": "Itens",
    "started_at": "Inicio", "duration_s": "Duracao (s)", "duration_ms": "Duracao (ms)",
    "error_message": "Erro", "normalizado": "Normalizado (R$/kg | R$/un)",
    "store_id": "Loja ID", "max_retries": "Tentativas Max",
    "timeout_seconds": "Timeout (s)", "rate_limit_per_minute": "Rate Limit/min",
    "cron_expression": "Cron", "timezone": "Fuso Horario",
    "last_run": "Ultima Execucao", "next_run": "Proxima Execucao",
    "created_at": "Criado Em", "updated_at": "Atualizado Em",
    "wins": "Dias como mais barata",
    "city": "Cidade", "zone": "Bairro/Zona",
}


def _pt_cols(df):
    """Rename DataFrame columns from DB names to PT display names."""
    rename = {c: _COL_PT[c] for c in df.columns if c in _COL_PT}
    return df.rename(columns=rename) if rename else df


@st.cache_data(ttl=600)
def load_ingredients():
    with open(INGREDIENTS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("ingredients", [])


@st.cache_data(ttl=600)
def _cached_load_stores_yaml():
    with open("config/stores.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("stores", [])


@st.cache_data(ttl=300)
def _cached_get_all_stores(include_inactive=False):
    return get_all_stores(include_inactive)


@st.cache_data(ttl=300)
def _cached_get_all_ingredients(include_inactive=False):
    return get_all_ingredients(include_inactive)


@st.cache_data(ttl=300)
def _cached_get_active_ingredients():
    return get_active_ingredients()


@st.cache_data(ttl=300)
def _cached_get_all_schedules(include_disabled=False):
    return get_all_schedules(include_disabled)


@st.cache_data(ttl=300)
def _cached_get_all_recipients(include_inactive=False):
    return get_all_recipients(include_inactive)


@st.cache_data(ttl=300)
def _cached_get_all_alert_rules(include_disabled=False):
    return get_all_alert_rules(include_disabled)


@st.cache_data(ttl=300)
def _cached_get_scrape_frequency(store_id=None, tier=None):
    return get_scrape_frequency(store_id, tier)


@st.cache_data(ttl=300)
def _cached_get_latest_prices(valid_only=True):
    return get_latest_prices(valid_only)


@st.cache_data(ttl=60)
def _cached_get_review_queue():
    return get_review_queue()


@st.cache_data(ttl=60)
def _cached_get_price_history(ingredient: str, days: int = 30, valid_only: bool = False):
    return get_price_history(ingredient, days, valid_only)


@st.cache_data(ttl=60)
def _cached_get_all_current_prices(valid_only: bool = True):
    return get_all_current_prices(valid_only=valid_only, limit=2000)


def _export_csv_button(df, filename: str, label: str = "Exportar CSV", key: str = "csv_export", full_width: bool = True):
    """Botao de export CSV com feature flag."""
    w = 'stretch' if full_width else 'content'
    if get_config("features.export.csv_enabled", True):
        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(label, csv_data, filename, "text/csv", key=key, width=w)
    else:
        st.download_button(label, data="", disabled=True,
            help="Exportacao desabilitada em config/features.yaml",
            key=f"{key}_disabled", width=w)


def require_auth():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        inject_css()
        render_login()
        return False
    return True


def _safe_image_url(url: str) -> str:
    """Returns a valid image URL or empty string (shows placeholder)."""
    if not url or not isinstance(url, str):
        return ""
    url = url.strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return ""


def _sanitize(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _get_repo_from_git() -> str:
    try:
        import subprocess  # nosec B404
        import shutil
        git_path = shutil.which("git")
        if not git_path:
            return "CustoDoce/CustoDoce"
        origin = subprocess.run(  # nosec B603  # noqa: S603
            [git_path, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        if origin:
            repo = origin.replace("https://github.com/", "").replace(".git", "")
            repo = repo.replace("git@github.com:", "")
            return repo
    except Exception:
        logger.warning("Falha ao obter repo do git, usando fallback")
    return os.environ.get("GH_REPO", "user/CustoDoce")


def _get_kg(df):
    vals = df["normalized"].apply(
        lambda x: x.get("price_per_kg", 0) if isinstance(x, dict) else 0
    )
    return vals


def _render_kpi_prices(df):
    total = len(df)
    lojas = df["store_name"].nunique() if "store_name" in df.columns else 0
    matched = len(df[df.get("confidence", 1) >= 0.8])
    review = len(_cached_get_review_queue())
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f'<div class="cd-metric"><div class="label">Total Precos</div><div class="value">{total}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="cd-metric"><div class="label">Confiaveis >=80%</div><div class="value">{matched}</div></div>', unsafe_allow_html=True)
    with col_b:
        st.markdown(f'<div class="cd-metric"><div class="label">Lojas</div><div class="value">{lojas}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="cd-metric"><div class="label">Fila Revisao</div><div class="value">{review}</div></div>', unsafe_allow_html=True)


def _render_kpi_flyers(df):
    try:
        from services.flyer_service import get_recent_flyers
        flyers = get_recent_flyers(days=3)
        f_total = len(flyers) if flyers else 0
        f_processed = len([f for f in (flyers or []) if f.get("ocr_status") in ("done", "processed")])
        hoje = pd.Timestamp.utcnow().date()
        precos_hoje = 0
        desatualizados = 0
        if "collected_at" in df.columns:
            for val in df["collected_at"]:
                if pd.notna(val):
                    dt = pd.to_datetime(val)
                    if dt.tzinfo is not None:
                        dt = dt.replace(tzinfo=None)
                    if dt.date() == hoje:
                        precos_hoje += 1
                    if (pd.Timestamp.utcnow() - dt).days > 7:
                        desatualizados += 1
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f'<div class="cd-metric" style="border-left-color:#3B7DD8;"><div class="label">Flyers (3d)</div><div class="value">{f_total}</div></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="cd-metric" style="border-left-color:#F59E0B;"><div class="label">Precos Hoje</div><div class="value">{precos_hoje}</div></div>', unsafe_allow_html=True)
        with col_b:
            st.markdown(f'<div class="cd-metric" style="border-left-color:#10B981;"><div class="label">Processados</div><div class="value">{f_processed}</div></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="cd-metric" style="border-left-color:#EF4444;"><div class="label">Desatualizados (+7d)</div><div class="value">{desatualizados}</div></div>', unsafe_allow_html=True)
    except Exception:
        st.caption("Indicadores de flyers indisponiveis")


def _render_latest_prices(df):
    st.markdown("### Ultimos Precos")
    if df is None or df.empty:
        st.caption("Nenhum preco disponivel.")
        return
    cols = ["store_name", "ingredient_id", "raw_product", "raw_price", "raw_unit", "tier", "is_promotion", "valid_until", "confidence", "collected_at"]
    cols = [c for c in cols if c in df.columns]
    st.dataframe(_pt_cols(df[cols].sort_values("collected_at", ascending=False).head(100)), width='stretch', hide_index=True)


def _render_boxplot(df):
    if df is None or df.empty:
        st.caption("Dados insuficientes para boxplot.")
        return
    if "normalized" not in df.columns or not df["normalized"].notna().any():
        st.caption("Dados normalizados indisponiveis para boxplot.")
        return
    df_norm = df[df["normalized"].notna() & (df["price_per_kg"] > 0)].copy()
    if df_norm.empty:
        st.caption("Nenhum preco valido para boxplot.")
        return
    fig = px.box(df_norm, x="ingredient_id", y="price_per_kg", title="Preco por kg por Ingrediente",
                 labels={"ingredient_id": "Ingrediente", "price_per_kg": "R$/kg"},
                 color_discrete_sequence=[CD_ORANGE])
    st.plotly_chart(fig, width='stretch')


def _render_coverage_heatmap(df):
    st.markdown("### Cobertura de Coleta")
    try:
        ingredients = load_ingredients()
        ing_names = [i["canonical"] for i in ingredients[:11]]
        stores = sorted(df["store_name"].unique().tolist())
        if not stores or not ing_names:
            st.caption("Dados insuficientes para grade de cobertura.")
            return
        matrix = []
        for ing in ing_names:
            row = {"Ingrediente": ing}
            for store in stores[:10]:
                row[store] = "---"
            for _, p in df[df["ingredient_id"] == ing].iterrows():
                s = p.get("store_name", "")
                if s not in row:
                    continue
                ts = p.get("collected_at", "")
                if pd.notna(ts):
                    try:
                        dt = pd.to_datetime(ts)
                        if dt.tzinfo is not None:
                            dt = dt.replace(tzinfo=None)
                        now = datetime.now()
                        days_ago = (now - dt).days
                        row[s] = "hoje" if days_ago <= 3 else "semana" if days_ago <= 7 else "antigo"
                    except Exception as e:
                        row[s] = f"erro: {e}"
                        logger.warning("Coverage heatmap: ts=%s err=%s", ts, e)
            matrix.append(row)
        df_heat = pd.DataFrame(matrix)

        def color_cell(val):
            if val == "hoje":
                return "background:#D1FAE5;color:#065F46;font-weight:700;"
            if val == "semana":
                return "background:#FEF3C7;color:#92400E;font-weight:700;"
            if val == "antigo":
                return "background:#FEE2E2;color:#991B1B;font-weight:700;"
            if isinstance(val, str) and val.startswith("erro"):
                return "background:#FEE2E2;color:#DC2626;font-weight:700;"
            return "background:#F3F4F6;color:#9CA3AF;"

        # Legenda
        st.markdown(
            '<div style="display:flex;gap:1rem;margin-bottom:0.5rem;font-size:0.85rem;">'
            '<span style="display:flex;align-items:center;gap:0.3rem;">'
            '<span style="width:14px;height:14px;background:#D1FAE5;border:1px solid #A7F3D0;border-radius:3px;"></span>'
            '<strong style="color:#065F46;">hoje</strong> <span style="color:#6B7280;">(≤3 dias)</span>'
            '</span>'
            '<span style="display:flex;align-items:center;gap:0.3rem;">'
            '<span style="width:14px;height:14px;background:#FEF3C7;border:1px solid #FDE68A;border-radius:3px;"></span>'
            '<strong style="color:#92400E;">semana</strong> <span style="color:#6B7280;">(4–7 dias)</span>'
            '</span>'
            '<span style="display:flex;align-items:center;gap:0.3rem;">'
            '<span style="width:14px;height:14px;background:#FEE2E2;border:1px solid #FECACA;border-radius:3px;"></span>'
            '<strong style="color:#991B1B;">antigo</strong> <span style="color:#6B7280;">(>7 dias)</span>'
            '</span>'
            '<span style="display:flex;align-items:center;gap:0.3rem;">'
            '<span style="width:14px;height:14px;background:#F3F4F6;border:1px solid #E5E7EB;border-radius:3px;"></span>'
            '<span style="color:#9CA3AF;">sem dados</span>'
            '</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        st.dataframe(df_heat.style.map(color_cell), width='stretch', hide_index=True)
    except Exception as e:
        st.caption(f"Grade indisponivel: {e}")


def _render_variation_alerts(df):
    st.markdown("### Alertas de Variacao")
    alert_pct = get_config("features.alerts.price_variation_pct", 15)
    try:
        alerts_found = False
        for ing in load_ingredients()[:6]:
            ing_name = ing["canonical"]
            ing_prices = df[df["ingredient_id"] == ing_name]
            if ing_prices.empty:
                continue
            recent = ing_prices[ing_prices["price_per_kg"] > 0]
            if recent.empty:
                continue
            avg = recent["price_per_kg"].mean()
            current = recent.sort_values("collected_at").iloc[-1]["price_per_kg"]
            if avg <= 0 or current <= 0:
                continue
            change = ((current - avg) / avg) * 100
            if abs(change) > alert_pct:
                alerts_found = True
                icon = "subiu" if change > 0 else "caiu"
                color = "#EF4444" if change > 0 else "#10B981"
                st.markdown(
                    f'<div style="padding:0.5rem 0.75rem;border-radius:8px;background:#FFF;border:1px solid #F0E6DB;margin-bottom:0.5rem;display:flex;justify-content:space-between;">'
                    f"<span><strong>{ing_name}</strong> {icon} <strong>{abs(change):.0f}%</strong></span>"
                    f'<span style="color:{color};font-weight:700;">R$ {current:.2f}/kg (media: R$ {avg:.2f}/kg)</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
        if not alerts_found:
            st.caption(f"Nenhuma variacao significativa detectada (limite: ±{alert_pct:.0f}%).")
    except Exception as e:
        st.caption(f"Alertas indisponiveis: {e}")


def _valid_only_toggle():
    key = "global_valid_only"
    if key not in st.session_state:
        st.session_state[key] = True
    return st.toggle(
        "So vigentes",
        key=key,
        help="Mostrar apenas precos dentro do periodo de vigencia",
    )


def tab_visao_geral():
    section_title("Visao Geral", "Resumo do estado atual dos precos")
    valid_only = _valid_only_toggle()
    prices = _cached_get_latest_prices(valid_only=valid_only)
    if not prices:
        info_box("Nenhum preco coletado ainda. Aguarde a primeira execucao do scraper.", "info")
        return

    df = pd.DataFrame(prices)
    df["price_per_kg"] = _get_kg(df)
    _render_kpi_prices(df)
    _render_kpi_flyers(df)
    _render_latest_prices(df)
    _render_boxplot(df)
    _render_coverage_heatmap(df)
    _render_variation_alerts(df)


def tab_precos():
    section_title("Buscar Precos", "Compare precos entre lojas por ingrediente")
    valid_only = _valid_only_toggle()
    ingredients = load_ingredients()
    ingredient_options = {i["canonical"]: i for i in ingredients}
    selected = st.selectbox(
        "Selecione o ingrediente",
        options=list(ingredient_options.keys()),
        index=0 if ingredient_options else 0,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        sort_options = {"R$/kg": "price_per_kg", "R$/un": "price_per_un", "Preço bruto": "raw_price"}
        sort_label = st.selectbox("Ordenar por", list(sort_options.keys()))
        sort_by = sort_options[sort_label]
    with col2:
        sort_order = st.selectbox("Ordem", ["Crescente", "Decrescente"])
    with col3:
        limit = st.number_input("Limite", min_value=5, max_value=100, value=30)

    if st.button("Buscar", type="primary"):
        with st.spinner("Buscando precos..."):
            prices = search_prices(
                selected, sort_by=sort_by, sort_order=sort_order, limit=limit,
                valid_only=valid_only,
            )
        if prices:
            df = pd.DataFrame(prices)
            df["price_per_kg"] = _get_kg(df)

            st.success(f"{len(df)} precos encontrados para **{selected}**")

            top3 = (
                df[df["price_per_kg"] > 0]
                .sort_values("price_per_kg")
                .head(3)
            )
            if not top3.empty:
                st.markdown(
                    '<div style="display:flex;gap:0.75rem;margin:1rem 0;flex-wrap:wrap;">',
                    unsafe_allow_html=True,
                )
                colors = ["#F59E42", "#E8739A", "#3B7DD8"]
                for i, (_, row) in enumerate(top3.iterrows()):
                    store = _sanitize(row.get("store_name", "?"))
                    city = _sanitize(row.get("city", ""))
                    zone = _sanitize(row.get("zone", ""))
                    location = f"{city}" + (f" - {zone}" if zone else "")
                    product = _sanitize(row.get("raw_product", "?"))[:40]
                    ppk = row.get("price_per_kg", 0)
                    raw_p = row.get("raw_price", 0)
                    unit = row.get("raw_unit", "")
                    st.markdown(
                        f'<div style="flex:1;min-width:160px;background:#FFF;'
                        f'border-radius:12px;padding:1rem;border:1px solid #F0E6DB;'
                        f'border-top:4px solid {colors[i]};'
                        f'box-shadow:0 2px 8px rgba(0,0,0,0.04);">'
                        f'<div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;'
                        f"color:#8B7355;\">{i+1}o mais barato</div>"
                        f'<div style="font-size:1.25rem;font-weight:800;color:#3D2C1E;'
                        f"margin:0.25rem 0;\">R$ {ppk:.2f}/kg</div>"
                        f'<div style="font-size:0.85rem;color:#6B7280;">{store}</div>'
                        f'<div style="font-size:0.75rem;color:#9CA3AF;">{location}</div>'
                        f'<div style="font-size:0.75rem;color:#9CA3AF;">{product}</div>'
                        f'<div style="font-size:0.75rem;color:#9CA3AF;">'
                        f"R$ {raw_p:.2f} {unit}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                st.markdown("</div>", unsafe_allow_html=True)

            if "normalized" in df.columns:
                df_plot = df[df["normalized"].notna() & (df["price_per_kg"] > 0)].copy()
                if not df_plot.empty:
                    fig = px.bar(
                        df_plot.head(20),
                        x="store_name",
                        y="price_per_kg",
                        hover_data=["raw_product", "raw_price", "raw_unit"],
                        title=f"{selected} - Preco por kg",
                        labels={"store_name": "Loja", "price_per_kg": "R$/kg"},
                        color="store_name",
                        color_discrete_sequence=[
                            CD_ORANGE, CD_PINK, CD_BLUE,
                            "#FBBF5E", "#60A5FA", "#C94D78",
                            "#F59E42", "#E8739A", "#3B7DD8",
                        ],
                    )
                    fig.update_layout(showlegend=False)
                    st.plotly_chart(fig, width='stretch')

            display_cols = [
                "store_name",
                "brand",
                "raw_product",
                "raw_price",
                "raw_unit",
                "tier",
                "is_promotion",
                "valid_until",
                "confidence",
                "collected_at",
                "city",
                "zone",
            ]
            display_cols = [c for c in display_cols if c in df.columns]

            def format_norm(p):
                if isinstance(p, dict):
                    return (
                        f"R$ {p.get('price_per_kg', 0):.2f}/kg | "
                        f"R$ {p.get('price_per_un', 0):.2f}/un"
                    )
                return ""

            if "normalized" in df.columns:
                df["normalizado"] = df["normalized"].apply(format_norm)
                display_cols = display_cols + ["normalizado"]

            # Format collected_at to pt-BR datetime
            if "collected_at" in df.columns:
                df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True, errors="coerce").dt.strftime("%d/%m/%Y %H:%M")

            # Legenda das colunas
            with st.expander("ℹ️ Legenda das colunas", expanded=False):
                st.markdown("""
                **Normalizado** — Preço padronizado para comparação: `R$ XX.XX/kg | R$ YY.YY/un`
                **Confiança** — Qualidade do match produto→ingrediente (1.0=exato, 0.8+=fuzzy, <0.8=revisão)
                **Tier** — Nível da loja (1=PDF direto, 2=E-commerce, 3=Agregadores, 4=Manual)
                **Promoção** — Detectado automaticamente por palavras-chave (PROMO, OFERTA, etc.)
                **Válido até** — Data fim da promoção/preço (se informada no folheto)
                **Coletado em** — Data/hora da coleta (fuso BR)
                **Cidade / Bairro** — Local da unidade onde o preço foi coletado
                """)

            df_display = df[display_cols].head(limit).copy()
            min_price_idx = None
            if "price_per_kg" in df.columns and sort_by in df.columns:
                price_per_kg_series = df_display.get("price_per_kg")
                valid = df_display[price_per_kg_series > 0].index if price_per_kg_series is not None else pd.Index([])
                if not valid.empty:
                    if sort_order == "Crescente":
                        min_price_idx = df_display.loc[valid, sort_by].idxmin()
                    else:
                        min_price_idx = df_display.loc[valid, sort_by].idxmax()

            if min_price_idx is not None:
                def highlight_row(s):
                    return (
                        ["background:#FEF3C7;font-weight:700;"] * len(s)
                        if s.name == min_price_idx
                        else [""] * len(s)
                    )
                styled = df_display.style.apply(highlight_row, axis=1)
                st.dataframe(_pt_cols(styled.data), width='stretch', hide_index=True)
            else:
                st.dataframe(_pt_cols(df_display), width='stretch', hide_index=True)

            _export_csv_button(
                df_display,
                f"precos_{selected}_{datetime.utcnow().strftime('%Y%m%d')}.csv",
                key=f"csv_precos_{selected}",
            )
        else:
            info_box(f"Nenhum preco encontrado para '{selected}'", "warning")


def _format_kg(p):
    if isinstance(p, dict):
        return p.get("price_per_kg", 0)
    return 0

def tab_historico():
    section_title("Historico de Precos", "Tendencias e variacoes ao longo do tempo")
    valid_only = _valid_only_toggle()
    ingredients = load_ingredients()
    options = [i["canonical"] for i in ingredients]
    selected = st.selectbox("Ingrediente", options)

    col1, col2 = st.columns(2)
    with col1:
        days = st.slider("Periodo (dias)", 7, 365, 90)
    with col2:
        chart_type = st.selectbox("Tipo de grafico", ["Linha (preco bruto)", "Linha (R$/kg)", "Dispersao"])
    load = st.button("Carregar", type="primary")

    if load:
        with st.spinner("Carregando historico..."):
            history = _cached_get_price_history(selected, days=days, valid_only=valid_only)
        if not history:
            info_box(f"Nenhum historico disponivel para '{selected}' no periodo.", "info")
            return

        df = pd.DataFrame(history)
        df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True, format="ISO8601", errors="coerce")
        df = df.sort_values("collected_at")

        # Format collected_at to pt-BR datetime for display
        if "collected_at" in df.columns:
            df["collected_at_display"] = df["collected_at"].dt.strftime("%d/%m/%Y %H:%M")

        df["price_per_kg"] = df["normalized"].apply(_format_kg)
        y_col = "price_per_kg" if "R$/kg" in chart_type else "raw_price"
        y_label = "R$/kg" if "R$/kg" in chart_type else "Preco (R$)"
        title_suffix = " - Preco por kg" if "R$/kg" in chart_type else " - Preco bruto"

        if "Dispersao" in chart_type:
            fig = px.scatter(
                df, x="collected_at", y=y_col, color="store_name",
                hover_data=["store_name", "raw_product", "raw_price"],
                title=f"{selected}{title_suffix} ({days} dias)",
                labels={"collected_at": "Data", y_col: y_label, "store_name": "Loja"},
                color_discrete_sequence=[CD_ORANGE, CD_PINK, CD_BLUE, "#FBBF5E", "#60A5FA", "#C94D78"],
                opacity=0.7,
            )
        else:
            fig = px.line(
                df, x="collected_at", y=y_col, color="store_name",
                title=f"{selected}{title_suffix} ({days} dias)",
                labels={"collected_at": "Data", y_col: y_label, "store_name": "Loja"},
                color_discrete_sequence=[CD_ORANGE, CD_PINK, CD_BLUE, "#FBBF5E", "#60A5FA", "#C94D78"],
            )
            fig.update_traces(mode="lines+markers")
        st.plotly_chart(fig, width='stretch')

        col_a, col_b, col_c, col_d = st.columns(4)
        valid = df[df[y_col] > 0] if y_col == "price_per_kg" else df
        if not valid.empty:
            col_a.metric("Preco Medio", f"R$ {valid[y_col].mean():.2f}")
            col_b.metric("Menor Preco", f"R$ {valid[y_col].min():.2f}")
            col_c.metric("Maior Preco", f"R$ {valid[y_col].max():.2f}")
            col_d.metric("Variacao", f"{(valid[y_col].max() / valid[y_col].min() - 1) * 100:.0f}%" if valid[y_col].min() > 0 else "—")

        st.markdown("### Cobertura por Loja")
        store_stats = df.groupby("store_name").agg(
            Coletas=("collected_at", "count"),
            Preco_Medio=(y_col, "mean"),
            Ultima_Coleta=("collected_at", "max")
        ).reset_index()
        store_stats.columns = ["Loja", "Coletas", "Preco Medio (R$)", "Ultima Coleta"]
        store_stats = store_stats.sort_values("Ultima Coleta", ascending=False)
        st.dataframe(_pt_cols(store_stats), width='stretch', hide_index=True)

        st.markdown("### Dados Brutos")
        # Legenda das colunas
        with st.expander("ℹ️ Legenda das colunas", expanded=False):
            st.markdown("""
            **Normalizado** — Preço padronizado: `R$ XX.XX/kg | R$ YY.YY/un`
            **R$/kg** — Preço por kg (calculado do Normalizado)
            **Confiança** — Match produto→ingrediente (1.0=exato, 0.8+=fuzzy, <0.8=revisão)
            **Promoção** — Detectado por palavras-chave (PROMO, OFERTA, etc.)
            **Válido até** — Data fim da promoção/preço
            **Coletado em** — Data/hora da coleta (fuso BR)
            **Cidade / Bairro** — Local da unidade onde o preço foi coletado
            """)

        display_cols = [c for c in ["store_name", "brand", "raw_product", "raw_price", "raw_unit", "is_promotion", "valid_until", "collected_at_display", "city", "zone"] if c in df.columns]
        if "price_per_kg" in df.columns:
            df["R$/kg"] = df["price_per_kg"].apply(lambda x: f"R$ {x:.2f}" if x > 0 else "—")
            display_cols.append("R$/kg")
        st.dataframe(_pt_cols(df[display_cols].tail(100)), width='stretch', hide_index=True)

        _export_csv_button(
            store_stats,
            f"cobertura_{selected}_{datetime.utcnow().strftime('%Y%m%d')}.csv",
            "Exportar Cobertura CSV",
            key="csv_cobertura",
        )
        _export_csv_button(
            df[display_cols],
            f"historico_{selected}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv",
            "Exportar Dados Brutos CSV",
            key="csv_historico",
        )


def _flyer_status_color(status):
    m = {"done": "#10B981", "processed": "#10B981", "pending": "#F59E0B", "failed": "#EF4444", "error": "#EF4444"}
    return m.get(status.lower(), "#6B7280")

def _flyer_status_label(status):
    status = "done" if status == "processed" else status
    m = {"done": "processado", "pending": "pendente", "failed": "falha", "error": "falha"}
    return m.get(status.lower(), status)

def tab_flyers():
    section_title("Flyers & OCR", "Folhetos coletados e status de processamento")
    try:
        from services.flyer_service import get_recent_flyers

        flyers = get_recent_flyers(days=90)
        if not flyers:
            info_box("Nenhum flyer coletado ainda.", "info")
            return

        df = pd.DataFrame(flyers)
        df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True, format="ISO8601")

        total = len(df)
        processed = len(df[df["ocr_status"].isin(["done", "processed"])]) if "ocr_status" in df.columns else 0
        pending = len(df[df["ocr_status"].isin(["pending", "error", "failed"])]) if "ocr_status" in df.columns else 0
        total_products = int(df["products_extracted"].sum()) if "products_extracted" in df.columns else 0

        st.markdown(
            '<div class="cd-kpi-row" style="display:flex;gap:0.75rem;margin-bottom:1rem;">'
            f'<div style="flex:1;"><div class="cd-metric"><div class="label">Total Flyers</div><div class="value">{total}</div></div></div>'
            f'<div style="flex:1;"><div class="cd-metric"><div class="label">Processados</div><div class="value">{processed}</div></div></div>'
            f'<div style="flex:1;"><div class="cd-metric"><div class="label">Pendentes</div><div class="value">{pending}</div></div></div>'
            f'<div style="flex:1;"><div class="cd-metric"><div class="label">Produtos Extraidos</div><div class="value">{total_products}</div></div></div>'
            "</div>",
            unsafe_allow_html=True,
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            status_filter = st.selectbox("Status", ["todos", "pendente", "processado", "falha"])
        with col2:
            source_filter = st.selectbox("Origem", ["todos", "tiendeo", "kimbino", "portafolhetos", "manual"])
        with col3:
            days_filter = st.selectbox("Periodo", [7, 15, 30, 60, 90], index=2)

        cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=days_filter)
        filtered = df[df["collected_at"] >= cutoff].copy()
        if status_filter != "todos":
            if status_filter == "pendente":
                filtered = filtered[filtered["ocr_status"].isin(["pending", "error", "failed"])]
            elif status_filter == "processado":
                filtered = filtered[filtered["ocr_status"].isin(["done", "processed"])]
            else:
                filtered = filtered[filtered["ocr_status"] == status_filter]
        if source_filter != "todos":
            filtered = filtered[filtered["source"] == source_filter]

        # ── Grid interativo de flyers ──
        cols_per_row = 4
        rows_data = list(filtered.head(50).iterrows())
        for row_idx in range(0, len(rows_data), cols_per_row):
            cols = st.columns(cols_per_row)
            for col_idx in range(cols_per_row):
                idx = row_idx + col_idx
                if idx >= len(rows_data):
                    cols[col_idx].empty()
                    continue
                _, f = rows_data[idx]
                status = f.get("ocr_status", "pending")
                color = _flyer_status_color(status)
                label = _flyer_status_label(status)
                store = _sanitize(f.get("store_name", "?"))
                title = _sanitize(f.get("flyer_title", f.get("title", ""))[:60])
                products = int(f.get("products_extracted", 0))
                collected = f["collected_at"].strftime("%d/%m") if pd.notna(f["collected_at"]) else "?"
                flyer_id = f.get("id", f"f_{idx}")
                img = f.get("image_url", "")
                img_url = _safe_image_url(img)
                with cols[col_idx], st.container(border=True):
                        img_html = html.escape(img_url)
                        if img_url:
                            st.markdown(
                                f'<div style="width:100%;min-height:100px;'
                                f'background:#F3F4F6;border-radius:8px;overflow:hidden;">'
                                f'<img src="{img_html}" '
                                f'style="width:100%;height:auto;display:block;" /></div>'
                                f'<a href="{img_html}" target="_blank" '
                                f'style="font-size:0.65rem;color:#6B7280;word-break:break-all;'
                                f'display:block;margin-top:0.25rem;">'
                                f'{img_html[:60]}...</a>',
                                unsafe_allow_html=True,
                            )
                        else:
                            if img:
                                st.markdown(
                                    f'<p style="font-size:0.7rem;color:#9CA3AF;word-break:break-all;">'
                                    f'{html.escape(img)}</p>',
                                    unsafe_allow_html=True,
                                )
                            else:
                                st.caption("Sem imagem")
                        st.markdown(
                            f'<div style="font-size:0.85rem;font-weight:700;">{store}</div>'
                            f'<div style="font-size:0.75rem;color:#6B7280;">{title}</div>'
                            f'<div style="display:flex;gap:0.5rem;font-size:0.7rem;margin-top:0.25rem;">'
                            f'<span style="color:{color};font-weight:700;">{label}</span>'
                            f'<span style="color:var(--cd-blue);font-weight:700;">{products} prod.</span>'
                            f'<span style="color:#9CA3AF;">{collected}</span>'
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                        if st.button("🔍 Ver detalhes", key=f"flyer_btn_{flyer_id}", width='stretch'):
                            st.session_state.selected_flyer_id = flyer_id
                            st.rerun()

        st.caption(f"Exibindo {min(len(filtered), 50)} de {len(filtered)} flyers")

        # ── Detalhe do flyer selecionado ──
        sel_id = st.session_state.get("selected_flyer_id")
        selected = None
        if sel_id:
            matches = filtered[filtered["id"] == sel_id]
            if not matches.empty:
                selected = matches.iloc[0]
        if selected is None and not filtered.empty:
            selected = filtered.iloc[0]

        if selected is not None:
            st.markdown("### Detalhe do Flyer")
            f_store = _sanitize(selected.get("store_name", "?"))
            f_region = _sanitize(selected.get("region", "?"))
            f_city = _sanitize(selected.get("city", "?"))
            f_ocr_status = selected.get("ocr_status", "pending")
            st.markdown(
                f'<div class="cd-flyer-detail">'
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;margin-bottom:1rem;">'
                f'<div><strong>Loja:</strong> {f_store}</div>'
                f'<div><strong>Regiao:</strong> {f_region}</div>'
                f'<div><strong>Cidade:</strong> {f_city}</div>'
                f'<div><strong>Status OCR:</strong> <span style="color:{_flyer_status_color(f_ocr_status)};font-weight:700;">{_flyer_status_label(f_ocr_status)}</span></div>'
                f'<div><strong>Produtos:</strong> {int(selected.get("products_extracted", 0))}</div>'
                f'<div><strong>Coleta:</strong> {pd.to_datetime(selected["collected_at"]).strftime("%d/%m/%Y %H:%M") if "collected_at" in selected else "?"}</div>'
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            raw_img = selected.get("image_url", "")
            img_url = _safe_image_url(raw_img)
            if img_url:
                col_img, col_dl = st.columns([3, 1])
                with col_img:
                    img_escaped = html.escape(img_url)
                    st.markdown(
                        f'<img src="{img_escaped}" '
                        f'style="width:100%;max-height:500px;object-fit:contain;border-radius:8px;" />'
                        f'<a href="{img_escaped}" target="_blank" '
                        f'style="font-size:0.7rem;color:#6B7280;word-break:break-all;display:block;margin-top:0.25rem;">'
                        f'Abrir imagem em nova aba</a>',
                        unsafe_allow_html=True,
                    )
                with col_dl:
                    try:
                        import httpx
                        resp = httpx.get(img_url, timeout=10)
                        if resp.status_code == 200:
                            ext = ".webp" if "webp" in resp.headers.get("content-type", "") else ".jpg"
                            st.download_button(
                                "⬇️ Baixar Flyer",
                                data=resp.content,
                                file_name=f"flyer_{selected.get('id', 'unknown')}{ext}",
                                mime=resp.headers.get("content-type", "image/jpeg"),
                                width='stretch',
                            )
                    except Exception as e:
                        st.caption(f"Erro ao baixar: {e}")
            elif raw_img:
                st.markdown(
                    f'<p style="font-size:0.75rem;color:#9CA3AF;word-break:break-all;">'
                    f'URL: <code>{html.escape(raw_img)}</code></p>',
                    unsafe_allow_html=True,
                )
            ocr_text = selected.get("ocr_text", "")
            if ocr_text:
                with st.expander("Texto OCR"):
                    st.code(ocr_text[:2000], language="text")
    except ImportError:
        info_box("Servico de flyers nao disponivel.", "warning")


def tab_revisao():
    section_title(
        "Fila de Revisao",
        "Itens com confidence < 80% aguardando classificacao",
    )
    review_items = _cached_get_review_queue()

    if review_items:
        st.markdown(f"**{len(review_items)} itens** aguardando revisao")

        for item in review_items[:50]:
            item_id = item.get("id")
            raw_product = item.get("raw_product", "?")
            confidence = item.get("confidence", 0)
            store_name = item.get("store_name", "?")
            source_type = item.get("source", "")
            raw_price = item.get("raw_price", 0)
            raw_unit = item.get("raw_unit", "")
            suggestions = item.get("suggestions", [])
            image_url = item.get("image_url", "")
            source_url = item.get("source_url", "")
            match_reason = item.get("match_reason", "")
            match_type = item.get("match_type", "")
            brand = item.get("brand", "")
            collected_at = item.get("collected_at", "")

            with st.container(border=True):
                # ── Row 1: Evidência visual (full width) ──
                img_url = _safe_image_url(image_url)
                if img_url:
                    img_escaped = html.escape(img_url)
                    st.markdown(
                        f'<img src="{img_escaped}" '
                        f'style="width:100%;max-height:300px;object-fit:contain;'
                        f'border-radius:8px;border:1px solid #E5E7EB;" />'
                        f'<a href="{img_escaped}" target="_blank" '
                        f'style="font-size:0.65rem;color:#6B7280;word-break:break-all;display:block;margin-top:0.25rem;">'
                        f'Abrir imagem em nova aba</a>',
                        unsafe_allow_html=True,
                    )
                elif source_url:
                    st.link_button(
                        "🔗 Abrir página do produto para conferir",
                        source_url,
                        width='stretch',
                        type="primary",
                    )
                    if image_url:
                        st.markdown(
                            f'<p style="font-size:0.7rem;color:#9CA3AF;word-break:break-all;margin-top:0.25rem;">'
                            f'URL imagem: <code>{html.escape(image_url)}</code></p>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.markdown(
                        '<div style="background:#FEF2F2;border:2px dashed #FCA5A5;'
                        'border-radius:8px;padding:1rem;text-align:center;color:#991B1B;">'
                        '❌ <strong>Sem imagem ou link de origem</strong><br/>'
                        'O scraper não capturou evidência visual deste item. '
                        'Classifique com base apenas no texto do produto.</div>',
                        unsafe_allow_html=True,
                    )
                    if image_url:
                        st.markdown(
                            f'<p style="font-size:0.7rem;color:#9CA3AF;word-break:break-all;margin-top:0.25rem;">'
                            f'URL imagem: <code>{html.escape(image_url)}</code></p>',
                            unsafe_allow_html=True,
                        )

                # ── Row 2: Info columns ──
                info_col, diag_col = st.columns([1, 1])

                with info_col:
                    st.markdown(f"**{raw_product}**")
                    st.markdown(
                        f"🏪 {store_name}"
                        f"{' · ' + source_type if source_type else ''}"
                        f" | 💰 R$ {float(raw_price):.2f} {raw_unit}"
                    )

                    origem_parts = []
                    if collected_at:
                        try:
                            dt = collected_at[:10] if "T" in str(collected_at) else str(collected_at)[:10]
                            origem_parts.append(f"📅 Coleta: {dt}")
                        except (TypeError, IndexError):
                            pass
                    if brand:
                        origem_parts.append(f"🏷️ Marca: {brand}")
                    if origem_parts:
                        st.caption(" | ".join(origem_parts))

                    # Confidence + match type
                    conf_pct = confidence * 100
                    st.progress(confidence)
                    if match_type:
                        badge_colors = {
                            "exact": ("green", "✅ Match exato"),
                            "fuzzy_canonical": ("orange", "🔍 Fuzzy (canônico)"),
                            "fuzzy_alias": ("orange", "🔍 Fuzzy (alias)"),
                            "word_subset": ("blue", "📝 Subconjunto de palavras"),
                        }
                        color, label = badge_colors.get(match_type, ("gray", match_type))
                        match_label = f":{color}[**{label}**]"
                    else:
                        match_label = f"Confiança: **{conf_pct:.0f}%**"
                    st.markdown(match_label)

                with diag_col:
                    st.markdown("**Diagnóstico**")
                    if match_reason:
                        parts = match_reason.split(" | ")
                        for p in parts:
                            if ":" in p:
                                k, _, v = p.partition(":")
                                st.markdown(f"- **{k.strip()}:** {v.strip()}")
                            else:
                                st.markdown(f"- {p}")

                        unmatched = ""
                        for p in parts:
                            if "não matcheadas" in p:
                                unmatched = p.split(":", 1)[-1].strip()
                        if unmatched:
                            st.markdown("**Palavras não matcheadas:**")
                            st.markdown(
                                f'<div style="background:#FEF2F2;border:1px solid #FCA5A5;'
                                f'border-radius:8px;padding:0.3rem 0.8rem;color:#991B1B;'
                                f'font-size:0.85rem;">{unmatched}</div>',
                                unsafe_allow_html=True,
                            )
                    else:
                        st.markdown(
                            f'<div style="background:#FEF3C7;border:1px solid #FCD34D;'
                            f'border-radius:8px;padding:0.3rem 0.8rem;color:#92400E;'
                            f'font-size:0.85rem;">'
                            f"Confiança {conf_pct:.0f}% abaixo do limiar de 80%"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

                # ── Row 2: Top 3 Candidates ──
                top3 = item.get("top3", [])
                if top3:
                    with st.expander(f"🎯 Top 3 Candidatos ({len(top3)})", expanded=False):
                        for i, c in enumerate(top3, 1):
                            c_score = c.get("score", 0)
                            c_type = c.get("match_type", "")
                            c_term = c.get("matched_term", "")
                            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "")
                            st.markdown(
                                f"{medal} **{c.get('canonical', '?')}** — "
                                f"{c_score:.0f}% ({c_type}) via '{c_term}'"
                            )
                            st.progress(c_score / 100.0)

                # ── Row 3: Actions ──
                st.divider()
                act_cols = st.columns([3, 1, 1])
                with act_cols[0]:
                    options = suggestions + ["Outro..."]
                    selected = st.selectbox(
                        "Classificar como ingrediente:",
                        options,
                        key=f"ingredient_{item_id}",
                        index=0 if suggestions else len(options) - 1,
                    )
                    if selected == "Outro..." or not suggestions:
                        st.text_input(
                            "Digite o nome do ingrediente",
                            key=f"custom_ingredient_{item_id}",
                            placeholder="Ex: Leite Condensado Integral",
                            label_visibility="collapsed",
                        )
                with act_cols[1]:
                    if st.button(
                        "✅ Aprovar", key=f"app_{item_id}", width='stretch'
                    ):
                        chosen = st.session_state.get(f"ingredient_{item_id}", "")
                        if chosen == "Outro...":
                            chosen = st.session_state.get(
                                f"custom_ingredient_{item_id}", ""
                            )
                        if chosen:
                            try:
                                approve_review_item(item_id, chosen)
                                st.rerun()
                            except Exception as e:
                                err_msg = str(e)
                                st.error(f"Erro ao aprovar: {err_msg}")
                                if "42P10" in err_msg:
                                    st.caption(
                                        "Execute no SQL Editor do Supabase:"
                                    )
                                    st.code(
                                        "ALTER TABLE prices "
                                        "ADD CONSTRAINT prices_ingredient_id_store_id_collected_at_key "
                                        "UNIQUE (ingredient_id, store_id, collected_at);",
                                        language="sql",
                                    )
                        else:
                            st.warning("Selecione um ingrediente antes de aprovar.")
                with act_cols[2]:
                    if st.button(
                        "❌ Rejeitar", key=f"rej_{item_id}", width='stretch'
                    ):
                        reject_review_item(item_id)
                        st.rerun()
    else:
        info_box("Nenhum item na fila de revisao!", "success")


def tab_lojas():
    section_title("Lojas", "Gerenciamento de lojas e categorias")

    stores = _cached_get_all_stores(include_inactive=True)

    # Carrega scrape_frequencies (todas, inclusive desativadas)
    client = get_service_client()
    freqs = client.table("scrape_frequencies").select("store_id,enabled").execute()
    freq_map = {}
    if freqs and freqs.data:
        for f in freqs.data:
            freq_map[f["store_id"]] = f["enabled"]

    tab_list, tab_form = st.tabs(["Lista", "Cadastrar/Editar"])

    with tab_list:
        if stores:
            # Merge stores com status real do scrape_frequencies
            enriched = []
            for s in stores:
                sid = s.get("id", "")
                enabled = freq_map.get(sid, False)  # sem entrada = desativado
                coverage = s.get("coverage", "") or ""
                motivo = ""
                if not enabled:
                    m = re.search(r'\(inativo\s*-\s*(.+?)\)', coverage)
                    if m:
                        motivo = m.group(1).strip().capitalize()
                    elif coverage:
                        motivo = coverage[:80]
                    else:
                        motivo = "Nao informado"
                enriched.append({**s, "_enabled": enabled, "_motivo": motivo})

            ativas = sum(1 for e in enriched if e["_enabled"])
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Lojas", len(stores))
            tiers = [s.get("tier", 3) for s in stores]
            col2.metric("Tiers", f"{min(tiers)}-{max(tiers)}" if tiers else "—")
            col3.metric("Ativas", ativas)
            col4.metric("Tipos", len({s.get("type") for s in stores if s.get("type")}))

            col_s1, col_s2, col_s3 = st.columns([2, 1, 1])
            with col_s3:
                status_filter = st.selectbox("Status", ["todas", "ativas", "desativadas"])
            with col_s2:
                tier_filter = st.selectbox("Filtrar Tier", ["todas", 1, 2, 3, 4])
            with col_s1:
                search = st.text_input("Buscar loja", placeholder="Nome ou cidade...")

            filtered = enriched
            if status_filter == "ativas":
                filtered = [e for e in filtered if e["_enabled"]]
            elif status_filter == "desativadas":
                filtered = [e for e in filtered if not e["_enabled"]]
            if tier_filter != "todas":
                filtered = [e for e in filtered if e.get("tier") == tier_filter]
            if search:
                q = search.lower()
                filtered = [e for e in filtered if q in e.get("name", "").lower() or any(q in c.lower() for c in e.get("city", []))]

            if filtered:
                df = pd.DataFrame(filtered)
                df["_status"] = df["_enabled"].map({True: "Ativa", False: "Desativada"})
                df["city_str"] = df["city"].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x) if x else "—")
                cols = ["name", "tier", "type", "city_str", "_status", "_motivo"]
                cols = [c for c in cols if c in df.columns]
                st.dataframe(_pt_cols(df[cols].head(100)), width='stretch', hide_index=True)
            else:
                info_box("Nenhuma loja encontrada com esse filtro.", "info")
        else:
            info_box("Nenhuma loja cadastrada.", "info")

    with tab_form:
        store_options = {f"{s['name']} ({'ativo' if s.get('is_active') else 'inativo'})": s for s in stores}
        sel = st.selectbox("Editar existente", ["— Nova —"] + list(store_options.keys()))

        if sel != "— Nova —":
            store = store_options[sel]
            default = store
        else:
            default = {
                "name": "", "tier": 2, "type": "website_catalog", "logistics": "retirada_local",
                "city": [], "zone": "", "url_pattern": "", "base_url": "", "api_endpoint": "",
                "search_url": "", "selectors": {}, "publish_day": "", "collection_method": "automated",
                "visit_frequency": "", "scraper": "", "contact": "", "coverage": "", "priority": 99, "is_active": True
            }

        freqs = _cached_get_scrape_frequency()
        freq_by_store = {}
        if freqs:
            for f in freqs:
                if f.get("store_id"):
                    freq_by_store[f["store_id"]] = f

        store_freq = freq_by_store.get(default.get("id"), {})

        with st.form("form_store"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Nome *", value=default.get("name", ""))
                tier = st.selectbox("Tier", [1, 2, 3, 4], index=[1, 2, 3, 4].index(default.get("tier", 2)))
                type_ = st.text_input("Tipo", value=default.get("type", ""))
                logistics = st.selectbox("Logística", ["retirada_local", "retirada_sp", "entrega", "online"], index=["retirada_local", "retirada_sp", "entrega", "online"].index(default.get("logistics", "retirada_local")))
                city_str = st.text_area("Cidades (uma por linha)", value="\n".join(default.get("city", [])))
                zone = st.text_input("Zona", value=default.get("zone", ""))
                url_pattern = st.text_input("URL Pattern (PDF)", value=default.get("url_pattern", ""))
            with col2:
                base_url = st.text_input("URL Base", value=default.get("base_url", ""))
                api_endpoint = st.text_input("API Endpoint (VTEX)", value=default.get("api_endpoint", ""), placeholder="https://loja.api/v2/produtos")
                search_url = st.text_input("URL de Busca", value=default.get("search_url", ""), placeholder="https://loja.com/busca?q=")
                selectors = st.text_area("Seletores JSON", value=str(default.get("selectors", {})))
                publish_day = st.selectbox("Dia Publicação", ["", "quarta", "quinta"], index=["", "quarta", "quinta"].index(default.get("publish_day", "")))
                collection_method = st.selectbox("Método Coleta", ["automatico", "visita_manual", "manual"], index=["automatico", "visita_manual", "manual"].index(default.get("collection_method", "automatico")))
                visit_frequency = st.text_input("Frequência Visita", value=default.get("visit_frequency", ""))
                scraper = st.text_input("Scraper", value=default.get("scraper", ""))
                contact = st.text_input("Contato", value=default.get("contact", ""))
                coverage = st.text_area("Cobertura", value=default.get("coverage", ""))
                priority = st.number_input("Prioridade", min_value=1, max_value=999, value=default.get("priority", 99))
                active = st.checkbox("Ativo", value=default.get("is_active", True))

            st.markdown("### Configurações de Coleta")
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                freq_min = st.number_input("Frequência (minutos)", min_value=60, value=store_freq.get("frequency_minutes", 1440), step=60)
                max_retries = st.number_input("Max Retries", min_value=0, max_value=5, value=store_freq.get("max_retries", 2))
            with col_f2:
                timeout = st.number_input("Timeout (segundos)", min_value=10, max_value=300, value=store_freq.get("timeout_seconds", 30), step=10)
                rate_limit = st.number_input("Rate Limit (req/min)", min_value=1, max_value=60, value=store_freq.get("rate_limit_per_minute", 10))

            if st.form_submit_button("Salvar", width='stretch'):
                if not name or not name.strip():
                    st.error("Nome da loja e obrigatorio.")
                    st.stop()
                city = [c.strip() for c in city_str.split("\n") if c.strip()]
                try:
                    selectors_json = json.loads(selectors) if selectors else {}
                except Exception:
                    selectors_json = {}
                try:
                    result = upsert_store({
                        "name": name,
                        "tier": tier,
                        "type": type_,
                        "logistics": logistics,
                        "city": city,
                        "zone": zone,
                        "url_pattern": url_pattern or None,
                        "base_url": base_url or None,
                        "api_endpoint": api_endpoint or None,
                        "search_url": search_url or None,
                        "selectors": selectors_json,
                        "publish_day": publish_day or None,
                        "collection_method": collection_method,
                        "visit_frequency": visit_frequency or None,
                        "scraper": scraper or None,
                        "contact": contact or None,
                        "coverage": coverage or None,
                        "priority": priority,
                        "is_active": active,
                    })
                    store_id = result.get("id") if result else None
                    if store_id:
                        upsert_scrape_frequency({
                            "store_id": store_id,
                            "frequency_minutes": freq_min,
                            "max_retries": max_retries,
                            "timeout_seconds": timeout,
                            "rate_limit_per_minute": rate_limit,
                            "enabled": True,
                        })
                    st.toast(f"Loja '{name}' salva!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar loja: {e}")

        if sel != "— Nova —":
            with st.popover("Excluir", width='stretch'):
                st.warning("Tem certeza que deseja excluir esta loja?")
                if st.button("Sim, excluir", type="primary", key="confirm_del_store"):
                    try:
                        delete_store(default["id"])
                        st.toast("Loja excluída!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir loja: {e}")


def _test_normalizer():
    st.markdown("### Testador Normalizer")
    raw_price = st.number_input("Preco bruto (R$)", min_value=0.0, value=42.90, step=0.1, key="norm_price")
    raw_unit = st.text_input("Unidade (ex: cx 12x395g, 2kg, 500g)", value="cx 12x395g", key="norm_unit")
    if st.button("Normalizar", type="primary", key="btn_norm"):
        try:
            from parsers.normalizer import normalize_price
            result = normalize_price(raw_price, raw_unit)
            st.json(result)
        except Exception as e:
            st.error(f"Erro: {e}")


def _test_matcher():
    st.markdown("### Testador Matcher")
    product = st.text_input("Nome do produto", value="Leite Condensado Moca 395g cx 12", key="match_product")
    if st.button("Match", type="primary", key="btn_match"):
        try:
            from parsers.matcher import match_ingredient, rank_ingredients
            ingredients = load_ingredients()
            ing, score, match_type = match_ingredient(product, ingredients)
            if ing:
                st.success(f"**Match:** {ing['canonical']} (confianca: {score:.1f}%, tipo: {match_type})")
                if score < 100:
                    candidates = rank_ingredients(product, ingredients, top_n=3)
                    with st.expander("Sugestoes"):
                        for c in candidates:
                            st.write(f"- {c[0]['canonical']} ({c[1]:.1f}%)")
            elif score >= 30:
                candidates = rank_ingredients(product, ingredients, top_n=3)
                with st.expander(f"Possiveis matches (score maximo: {score:.1f}%)"):
                    for c in candidates:
                        st.write(f"- {c[0]['canonical']} ({c[1]:.1f}%)")
            else:
                info_box("Nenhum match encontrado.", "warning")
        except Exception as e:
            st.error(f"Erro: {e}")


def tab_ingredientes():
    section_title("Ingredientes", "Ingredientes monitorados e seus aliases")

    ingredients = _cached_get_all_ingredients(include_inactive=True)
    tab_list, tab_form, tab_tester = st.tabs(["Lista", "Cadastrar/Editar", "Testadores"])

    with tab_list:
        if ingredients:
            df = pd.DataFrame(ingredients)
            df["active"] = df["active"].map({True: "✅", False: "⏸️"})
            df["aliases_str"] = df["aliases"].apply(lambda x: ", ".join(x[:5]) if x else "—")
            st.dataframe(
                _pt_cols(df[["canonical_name", "category", "aliases_str", "unit_target", "active"]]),
                width='stretch',
                hide_index=True,
            )
        else:
            st.info("Nenhum ingrediente cadastrado.")

    with tab_form:
        ing_options = {f"{i['canonical_name']} ({'ativo' if i['active'] else 'inativo'})": i for i in ingredients}
        sel = st.selectbox("Editar existente", ["— Novo —"] + list(ing_options.keys()))

        if sel != "— Novo —":
            ing = ing_options[sel]
            default = ing
        else:
            default = {
                "canonical_name": "", "category": "", "aliases": [],
                "brands": [], "search_terms": [], "unit_target": "kg", "active": True,
            }

        with st.form("form_ingredient"):
            st.markdown("##### Identificação")
            col1, col2 = st.columns([1, 1])
            with col1:
                canonical = st.text_input("Nome Canônico *", value=default["canonical_name"], key="ing_canonical")
                category = st.text_input("Categoria", value=default["category"], key="ing_category", placeholder="ex: lacteos, chocolates")
            with col2:
                unit_target = st.selectbox("Unidade Alvo", ["kg", "un", "g", "ml", "l"], index=["kg", "un", "g", "ml", "l"].index(default.get("unit_target", "kg")))
                active = st.checkbox("Ativo", value=default.get("active", True))

            st.markdown("##### Marcas e Busca")
            col_b1, col_b2 = st.columns([1, 1])
            with col_b1:
                brands_str = st.text_area(
                    "Marcas (uma por linha)",
                    value="\n".join(default.get("brands", [])),
                    help="Nomes de marca que este ingrediente pode ter. Ex: Moça, Nestlé, Melken",
                    placeholder="Moça\nNestlé\nMelken",
                )
            with col_b2:
                search_terms_str = st.text_area(
                    "Termos de Busca (um por linha)",
                    value="\n".join(default.get("search_terms", [])),
                    help="Palavras-chave para scrapers encontrarem este produto nos sites.",
                    placeholder="leite condensado\nleite cond\nleite condensado moça",
                )

            st.markdown("##### Aliases (variações do nome para match exato)")
            aliases_str = st.text_area(
                "Aliases (um por linha)",
                value="\n".join(default.get("aliases", [])),
                help="Cada alias é uma variação que o matcher reconhece como match exato (confiança 100%).",
                placeholder="Leite Condensado Integral 1kg\nLC Integral 395g\nLeite Cond. Moça cx 12",
            )

            st.caption(
                "💡 Dica: inclua variações com peso (`1kg`, `395g`), abreviatura (`LC`), "
                "nome invertido (`Moça Leite Cond`), e versão uppercase (`LEITE CONDENSADO`)."
            )

            # ── Suggest expander ──
            with st.expander("✨ Sugerir aliases automaticamente", expanded=False):
                _render_alias_suggestions(default, ingredients)

            if st.form_submit_button("Salvar", width='stretch'):
                if not canonical or not canonical.strip():
                    st.error("Nome canonico e obrigatorio.")
                    st.stop()
                aliases = [a.strip() for a in aliases_str.split("\n") if a.strip()]
                brands = [b.strip() for b in brands_str.split("\n") if b.strip()]
                search_terms = [s.strip() for s in search_terms_str.split("\n") if s.strip()]
                try:
                    upsert_ingredient({
                        "canonical_name": canonical,
                        "category": category or None,
                        "aliases": aliases,
                        "brands": brands,
                        "search_terms": search_terms,
                        "unit_target": unit_target,
                        "active": active,
                    })
                    st.toast(f"Ingrediente '{canonical}' salvo!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar ingrediente: {e}")

        if sel != "— Novo —":
            with st.popover("Excluir", width='stretch'):
                st.warning("Tem certeza que deseja excluir este ingrediente?")
                if st.button("Sim, excluir", type="primary", key="confirm_del_ing"):
                    try:
                        delete_ingredient(default["id"])
                        st.toast("Ingrediente excluído!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir ingrediente: {e}")

    with tab_tester:
        _test_normalizer()
        st.markdown("---")
        _test_matcher()

def _render_alias_suggestions(default: dict, all_ingredients: list[dict]):
    canon = st.session_state.get("ing_canonical", "").strip()
    if not canon:
        st.info("Digite o nome canônico acima para gerar sugestões.")
        return

    words = canon.split()
    abbr = "".join(w[0] for w in words if w[0].isalpha()).upper()
    qualifiers = {"integral", "grosso", "branco", "colorido", "morango", "sem", "açúcar", "acucar"}

    suggestions = set()
    for suffix in ["1kg", "500g", "395g", "200g", "800g", "12un", "cx 12"]:
        suggestions.add(f"{canon} {suffix}")
    for suffix in ["1kg", "500g", "395g"]:
        suggestions.add(f"{abbr} {suffix}")
    short = " ".join(w for w in words if w.lower() not in qualifiers)
    if short != canon and len(short) > 1:
        for s in ["1kg", "500g"]:
            suggestions.add(f"{short} {s}")
    if len(words) > 2:
        for s in ["1kg", "500g"]:
            suggestions.add(f"{' '.join(words[1:])} {s}")
    suggestions.add(canon.upper())

    existing = set(default.get("aliases", []))
    suggestions = sorted(s for s in suggestions if s not in existing)

    col_sug, col_ref = st.columns([2, 1])
    with col_sug:
        if suggestions:
            st.markdown("**Geradas a partir do nome canônico** — copie as linhas desejadas:")
            st.code("\n".join(suggestions[:12]), language="text")
        else:
            st.info("Todas as variações já estão na lista de aliases.")
    with col_ref:
        cat = default.get("category") or st.session_state.get("ing_category", "")
        if cat:
            same_cat = [
                i for i in all_ingredients
                if i.get("category") == cat and i.get("canonical_name") != canon
            ]
            refs = []
            for i in same_cat:
                refs.extend(i.get("aliases", [])[:3])
            if refs:
                st.markdown(f"**Aliases de `{cat}`:**")
                for a in refs[:8]:
                    st.code(a, language="text")


def _render_schedule_info():
    st.markdown("### Agendamento (GitHub Actions)")
    path = ".github/workflows/scrape.yml"
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        crons = re.findall(r"cron:\s*'([^']+)'", content)
        st.markdown(
            '<div style="display:flex;gap:0.75rem;flex-wrap:wrap;">'
            + "".join(
                f'<div tabindex="0" role="region" style="flex:1;min-width:200px;background:#FFF;padding:0.75rem 1rem;border-radius:10px;border:1px solid #F0E6DB;">'
                f'<div style="font-size:0.7rem;font-weight:700;color:#8B7355;">Cron {i+1}</div>'
                f'<div style="font-size:1rem;font-weight:800;color:#3D2C1E;">{c}</div>'
                f'</div>'
                for i, c in enumerate(crons)
            )
            + "</div>",
            unsafe_allow_html=True,
        )

        with st.expander("Editar Agendamento", expanded=False):
            st.markdown(
                '<p style="font-size:0.85rem;opacity:0.7;">'
                "Edite os cron expressions e clique em Salvar.</p>",
                unsafe_allow_html=True,
            )
            new_crons = []
            for i, c in enumerate(crons):
                new_c = st.text_input(
                    f"Cron {i+1}",
                    value=c,
                    key=f"cron_edit_{i}",
                    help="Formato: minuto hora dia mes dia-da-semana",
                )
                new_crons.append(new_c)
            if st.button("Salvar Agendamento", type="primary", width='stretch'):
                valid = True
                for c in new_crons:
                    if not re.match(r"^(\d+|\*)([-\/,*]\d*)*(\s+(\d+|\*)([-\/,*]\d*)*){4}$", c.strip()):
                        st.error(f"Cron invalido: '{c}' — use o formato 'minuto hora dia mes dia-semana'")
                        valid = False
                if not valid:
                    st.stop()
                backup_path = path + ".bak"
                shutil.copy2(path, backup_path)
                new_content = content
                for _i, (old, new) in enumerate(zip(crons, new_crons)):
                    new_content = new_content.replace(
                        f"cron: '{old}'", f"cron: '{new}'"
                    )
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                st.success("Agendamento atualizado! Backup salvo em scrape.yml.bak")

    except FileNotFoundError:
        info_box("Arquivo scrape.yml nao encontrado.", "warning")


def _get_store_tier(store_name: str, stores_config: list) -> int:
    """Retorna o tier de uma loja pelo nome."""
    for s in stores_config:
        if s.get("name") == store_name:
            return s.get("tier", 3)
    return 3


def _get_criticality_level(store_name: str, stores_config: list, last_success: str, days_failed: int) -> tuple[str, str]:
    """Retorna o nível de criticidade (label, cor) para uma loja."""
    tier = _get_store_tier(store_name, stores_config)

    if tier == 1 and days_failed >= 1:
        return "🔴 Crítico", "red"
    elif tier == 1 or (tier == 2 and days_failed >= 2):
        return "🟡 Alto", "orange"
    elif tier == 2 and days_failed >= 1:
        return "🟢 Médio", "yellow"
    else:
        return "⚪ Baixo", "gray"


def _render_scraper_health_dashboard(df: pd.DataFrame, stores_config: list):
    """Renderiza KPIs de saúde global dos scrapers."""
    total_stores = df["store_name"].nunique() if not df.empty else 0

    failed_stores = df[df["status"] == "failed"]["store_name"].nunique() if not df.empty else 0

    completed_with_data = df[(df["status"] == "completed") & (df["items_found"] > 0)]["store_name"].nunique() if not df.empty else 0

    active_pct = int(completed_with_data / total_stores * 100) if total_stores > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if active_pct >= 90:
            st.metric("Scrapers Ativos", f"{completed_with_data}/{total_stores}", f"{active_pct}% ✅", delta_color="normal")
        elif active_pct >= 70:
            st.metric("Scrapers Ativos", f"{completed_with_data}/{total_stores}", f"{active_pct}% ⚠️", delta_color="off")
        else:
            st.metric("Scrapers Ativos", f"{completed_with_data}/{total_stores}", f"{active_pct}% 🔴", delta_color="inverse")

    with col2:
        st.metric("Scrapers com Falha", failed_stores, delta=None)

    with col3:
        avg_items = int(df[df["items_found"] > 0]["items_found"].mean()) if not df.empty else 0
        st.metric("Média Itens/Loja", avg_items)

    with col4:
        last_complete = df[df["status"] == "completed"]["started_at"].max() if not df.empty else None
        if last_complete:
            st.metric("Última Coleta", str(last_complete)[:16])
        else:
            st.metric("Última Coleta", "N/A")


def _render_scraper_maintenance(_client_unused=None):
    st.markdown("### Scraper Health Console")

    stores_config = _cached_load_stores_yaml()

    try:
        from services.supabase_client import get_service_client
        client = get_service_client()
        with st.spinner("Carregando lojas..."):
            logs = (
                client.table("scraping_logs")
                .select("*")
                .order("started_at", desc=True)
                .limit(200)
                .execute()
            )

        if not logs.data:
            st.info("Nenhum log de scraping encontrado.")

            st.markdown("---")
            st.markdown("### Editor de Seletores (YAML)")
            _render_selector_editor(stores_config)
            return

        df = pd.DataFrame(logs.data)

        # Dashboard de Saúde
        _render_scraper_health_dashboard(df, stores_config)
        st.markdown("---")

        # Filtros avançados
        col1, col2, col3 = st.columns(3)
        with col1:
            filter_status = st.selectbox(
                "Status",
                ["Todos", "failed", "completed"],
                key="filter_status_maint"
            )
        with col2:
            filter_tier = st.selectbox(
                "Tier",
                ["Todos", "1", "2", "3"],
                key="filter_tier_maint"
            )
        with col3:
            show_only_failed = st.checkbox("Apenas com falhas", key="filter_failed_only")

        # Aplicar filtros
        filtered_df = df.copy()

        if filter_status != "Todos":
            filtered_df = filtered_df[filtered_df["status"] == filter_status]

        if filter_tier != "Todos":
            # Filtrar por tier, usando stores_config
            stores_in_tier = [s["name"] for s in stores_config if s.get("tier") == int(filter_tier)]
            filtered_df = filtered_df[filtered_df["store_name"].isin(stores_in_tier)]

        if show_only_failed:
            filtered_df = filtered_df[
                (filtered_df["status"] == "failed") |
                ((filtered_df["items_found"] == 0) & (filtered_df["status"] == "completed"))
            ]

        # Identificar falhas
        failed_mask = pd.Series([False] * len(filtered_df))
        if "status" in filtered_df.columns:
            failed_mask |= filtered_df["status"] == "failed"
        if "items_found" in filtered_df.columns:
            failed_mask |= (filtered_df["items_found"] == 0) & (filtered_df["status"] == "completed")

        failed_logs = filtered_df[failed_mask].copy()

        if failed_logs.empty:
            st.success("✅ Nenhum scraper com falhas com os filtros atuais!")
        else:
            # Agrupar por loja e calcular dias desde última execução
            failed_stores = failed_logs.groupby("store_name").first().reset_index()

            # Adicionar coluna de criticidade
            for idx, row in failed_stores.iterrows():
                store_name = row.get("store_name", "?")
                started_at = row.get("started_at", "")

# Calcular dias desde última execução
                days_ago = 0
                if started_at:
                    try:
                        if isinstance(started_at, str):
                            last_date = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                        else:
                            last_date = started_at
                        days_ago = (datetime.now() - last_date.replace(tzinfo=None)).days
                    except Exception:
                        days_ago = 0

                criticality, color = _get_criticality_level(store_name, stores_config, started_at, days_ago)
                failed_stores.loc[idx, "criticality"] = criticality
                failed_stores.loc[idx, "days_ago"] = days_ago

            # Ordenar por criticidade
            criticality_order = {"🔴 Crítico": 0, "🟡 Alto": 1, "🟢 Médio": 2, "⚪ Baixo": 3}
            failed_stores["crit_order"] = failed_stores["criticality"].map(criticality_order)
            failed_stores = failed_stores.sort_values("crit_order")

            st.markdown(f"#### ⚠️ Scrapers com Falhas ({len(failed_stores)})")

            for _, row in failed_stores.iterrows():
                store_name = row.get("store_name", "?")
                status = row.get("status", "?")
                items_found = row.get("items_found", 0)
                errors = row.get("errors", [])
                started_at = row.get("started_at", "?")
                criticality = row.get("criticality", "⚪ Baixo")
                days_ago = row.get("days_ago", 0)

                error_msg = errors[0] if errors else "Sem detalhes"

                # Cabeçalho com criticidade
                col_header, col_test, col_github = st.columns([3, 1, 1])
                with col_header:
                    st.markdown(f"**{criticality} {store_name}**")
                    st.caption(f"Status: `{status}` | Itens: {items_found} | Há {days_ago} dia(s)")

                # Botão testar
                with col_test:
                    if st.button("🔄 Testar", key=f"test_{store_name}"):
                        try:
                            import httpx
                            gh_token = os.environ.get("GH_PAT", "")
                            repo = os.environ.get("GH_REPO") or _get_repo_from_git()
                            resp = httpx.post(
                                f"https://api.github.com/repos/{repo}/actions/workflows/scrape.yml/dispatches",
                                json={"ref": "master", "inputs": {"force_store": store_name}},
                                headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"},
                                timeout=30,
                            )
                            if resp.status_code in (200, 204):
                                st.success(f"Workflow disparado para {store_name}!")
                            else:
                                st.error(f"Erro GitHub API: {resp.status_code}")
                        except Exception as e:
                            st.error(f"Erro ao testar: {e}")

                # Expander com detalhes
                with st.expander(f"Ver detalhes - {store_name}", expanded=False):
                    st.code(str(error_msg), language=None)

                    # Botão criar issue
                    if st.button("📝 Criar Issue no GitHub", key=f"github_{store_name}"):
                        _create_github_issue(store_name, error_msg, status, items_found)

                    # Histórico gráfico
                    store_history = df[df["store_name"] == store_name].head(10)
                    if len(store_history) > 1:
                        st.markdown("**Histórico de Execuções:**")
                        fig = px.bar(
                            store_history.sort_values("started_at"),
                            x="started_at",
                            y="items_found",
                            color="status",
                            color_discrete_map={"failed": "red", "completed": "green"},
                            title=f"Últimas {len(store_history)} execuções"
                        )
                        st.plotly_chart(fig, width='stretch')

    except Exception as e:
        info_box(f"Erro ao carregar scrapers com falhas: {e}", "danger")

    # Editor de seletores
    st.markdown("---")
    st.markdown("### Editor de Seletores (YAML)")
    _render_selector_editor(stores_config)


def _render_selector_editor(stores_config: list):
    """Renderiza o editor de seletores."""
    stores = stores_config or _cached_load_stores_yaml()
    config_path = Path(__file__).resolve().parent.parent / "config" / "stores.yaml"
    if not stores:
        st.warning("Nenhuma loja configurada.")
        return

    store_names = [s.get("name", f"store_{i}") for i, s in enumerate(stores)]
    selected_idx = st.selectbox(
        "Selecione a loja para ajustar seletores",
        range(len(store_names)),
        format_func=lambda x: store_names[x],
        key="selector_store_idx"
    )

    if selected_idx is not None:
        store = stores[selected_idx]
        current_selectors = store.get("selectors", {})
        for sel in ["product_card", "product_name", "product_price", "product_validity"]:
            if sel not in current_selectors:
                current_selectors[sel] = []

        st.markdown("**Seletores CSS (separados por vírgula)**")
        new_selectors = {}
        for sel_key in ["product_card", "product_name", "product_price", "product_validity"]:
            val = st.text_area(
                sel_key,
                value=", ".join(current_selectors.get(sel_key, [])),
                key=f"sel_{sel_key}_{selected_idx}",
                height=80
            )
            new_selectors[sel_key] = [v.strip() for v in val.split(",") if v.strip()]

        if not st.session_state.get("confirm_stores_save"):
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("Confirmar salvamento?", type="primary", key="confirm_stores_btn"):
                    st.session_state.confirm_stores_save = True
                    st.rerun()
            with col2:
                st.caption("💡 Clique em confirmar para ativar o salvamento.")
            st.stop()

        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("💾 Salvar Seletores", type="primary", key="save_selectors"):
                stores[selected_idx]["selectors"] = new_selectors
                try:
                    with open(config_path, "w", encoding="utf-8") as f:
                        yaml.dump({"stores": stores}, f, allow_unicode=True, default_flow_style=False)
                    st.success(f"✅ Seletores de **{store_names[selected_idx]}** atualizados!")

                    # Notificar via Telegram
                    _send_telegram_selector_update(store_names[selected_idx])
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")
                st.session_state.pop("confirm_stores_save", None)
        with col2:
            st.caption("💡 Os scrapers usarão os novos seletores na próxima execução.")


def _create_github_issue(store_name: str, error_msg: str, status: str, items_found: int):
    """Cria uma issue no GitHub para uma falha de scraper."""
    gh_pat = os.environ.get("GH_PAT")
    repo = os.environ.get("GITHUB_REPOSITORY", "CustoDoce/CustoDoce")

    if not gh_pat:
        st.warning("GH_PAT não configurado. Configure nas variáveis de ambiente.")
        return

    title = f"[BUG] Scraper {store_name} falhando"
    body = f"""## Descrição
Scraper da loja **{store_name}** está com falha.

**Status:** `{status}`
**Itens encontrados:** {items_found}

## Erro
```
{error_msg}
```

## Ações necessárias
1. Verificar se o site da loja está acessível
2. Atualizar seletores CSS se necessário
3. Testar após correção

---
_Issue criada automaticamente pelo CustoDoce Health Console_
"""

    try:
        import httpx
        resp = httpx.post(
            f"https://api.github.com/repos/{repo}/issues",
            headers={
                "Authorization": f"token {gh_pat}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={"title": title, "body": body, "labels": ["bug", "scraper"]},
            timeout=30,
        )
        if resp.status_code == 201:
            st.success(f"✅ Issue criada: {resp.json().get('html_url', '')}")
        else:
            st.error(f"Erro ao criar issue: {resp.status_code}")
    except Exception as e:
        st.error(f"Erro ao criar issue: {e}")


def _send_telegram_selector_update(store_name: str):
    """Envia notificação Telegram quando seletores são atualizados."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        return

    try:
        message = f"🔧 *Seletores Atualizados*\n\nLoja: *{store_name}*\n\nOs seletores CSS foram ajustados no CustoDoce. A próxima execução usará os novos valores."
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=15,
        )
    except Exception as e:
        logger.warning("Falha ao enviar atualizacao via Telegram: %s", e)


def tab_scrapers():
    section_title("Scrapers & Logs", "Execucao manual e acompanhamento de logs")
    _render_schedule_info()
    st.markdown("---")

    tab_logs, tab_agenda, tab_manutencao = st.tabs(["Logs Recentes", "Agendamentos", "Manutencao de Scrapers"])

    with tab_logs:
        col1, col2 = st.columns(2)
        with col1:
            if st.button(
                "Forcar Coleta Agora", type="primary", width='stretch'
            ) and not st.session_state.get("confirm_force_scrape"):
                st.session_state.confirm_force_scrape = True
                st.rerun()
            if st.session_state.get("confirm_force_scrape"):
                st.warning("Confirma disparo do workflow no GitHub Actions?")
                if st.button("Sim, disparar", key="confirm_force_yes"):
                    gh_pat = os.environ.get("GH_PAT")
                    repo = os.environ.get("GITHUB_REPOSITORY", "CustoDoce/CustoDoce")
                    if gh_pat:
                        resp = httpx.post(
                        f"https://api.github.com/repos/{repo}/dispatches",
                        headers={
                            "Authorization": f"token {gh_pat}",
                            "Accept": "application/vnd.github.v3+json",
                        },
                        json={"event_type": "manual_trigger"},
                        timeout=30,
                        )
                        if resp.status_code == 204:
                            st.success("Coleta disparada com sucesso!")
                        else:
                            st.error(f"Erro: {resp.status_code}")
                    else:
                        st.warning("GH_PAT nao configurado nas secrets do ambiente.")
                    st.session_state.pop("confirm_force_scrape", None)
                if st.button("Cancelar", key="confirm_force_no"):
                    st.session_state.pop("confirm_force_scrape", None)
                    st.rerun()
        with col2:
            st.info("Clique para acionar a coleta manual via GitHub Actions.")

        client = None
        try:
            from services.supabase_client import get_service_client

            client = get_service_client()
            with st.spinner("Carregando logs..."):
                logs = (
                    client.table("scraping_logs")
                    .select("*")
                    .order("started_at", desc=True)
                    .limit(50)
                    .execute()
                )
            if logs.data:
                df_logs = pd.DataFrame(logs.data)
                st.dataframe(
                    _pt_cols(df_logs[
                        [
                            "store_name",
                            "status",
                            "items_found",
                            "duration_ms",
                            "created_at",
                        ]
                    ])
                    if "store_name" in df_logs.columns
                    else _pt_cols(df_logs),
                    width='stretch',
                    hide_index=True,
                )
        except Exception as e:
            info_box(f"Erro ao carregar logs: {e}", "warning")

    with tab_agenda:
        st.caption("Gerencie agendamentos de coleta e relatórios.")
        schedules = _cached_get_all_schedules(include_disabled=True)
        if schedules:
            df = pd.DataFrame(schedules)
            df["enabled"] = df["enabled"].map({True: "✅ Ativo", False: "⏸️ Inativo"})
            st.dataframe(
                _pt_cols(df[["name", "cron_expression", "timezone", "enabled", "last_run", "next_run"]]),
                width='stretch',
                hide_index=True,
            )
        else:
            info_box("Nenhum agendamento encontrado.", "info")

        st.divider()

        with st.expander("➕  Novo Agendamento", expanded=False), st.form("form_schedule"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Nome único", placeholder="ex: coleta_diaria_tier1")
                cron = st.text_input("Expressão Cron", placeholder="0 12 * * 1,3,5")
                tz = st.text_input("Timezone", value="America/Sao_Paulo")
            with col2:
                enabled = st.checkbox("Ativo", value=True)
                payload = st.text_area("Payload JSON", value='{"force_full": false, "run_playwright": false}', height=100)
            if st.form_submit_button("Salvar", width='stretch'):
                try:
                    upsert_schedule({
                        "name": name,
                        "cron_expression": cron,
                        "timezone": tz,
                        "enabled": enabled,
                        "payload": json.loads(payload),
                    })
                    st.toast(f"Agendamento '{name}' salvo!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")

        if schedules:
            with st.expander("✏️  Editar / Executar / Excluir", expanded=False):
                for s in schedules:
                    cols = st.columns([3, 2, 2, 1, 1, 1])
                    cols[0].write(s["name"])
                    cols[1].write(s["cron_expression"])
                    cols[2].write("✅" if s["enabled"] else "⏸️")
                    if cols[3].button("Editar", key=f"edit_sched_{s['id']}", width='stretch'):
                        st.session_state[f"editing_sched_{s['id']}"] = True
                        st.rerun()
                    if cols[4].button("Executar", key=f"run_sched_{s['id']}", width='stretch', type="primary") and not st.session_state.get(f"confirm_exec_{s['id']}"):
                            st.session_state[f"confirm_exec_{s['id']}"] = True
                            st.rerun()
                    if st.session_state.get(f"confirm_exec_{s['id']}"):
                        st.warning("Confirma execucao?")
                        col_y, col_n = st.columns(2)
                        with col_y:
                            if st.button("Sim", key=f"exec_yes_{s['id']}"):
                                try:
                                    gh_token = os.environ.get("GH_PAT", "")
                                    repo = _get_repo_from_git()
                                    payload = s.get("payload") or {}
                                    resp = httpx.post(
                                        f"https://api.github.com/repos/{repo}/actions/workflows/scrape.yml/dispatches",
                                        json={"ref": "master", "inputs": payload},
                                        headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"},
                                        timeout=30,
                                    )
                                    if resp.status_code in (200, 204):
                                        st.success(f"Workflow disparado para '{s['name']}'!")
                                    else:
                                        st.error(f"Erro GitHub API: {resp.status_code} — {resp.text[:200]}")
                                except Exception as e:
                                    st.error(f"Erro ao executar: {e}")
                                st.session_state.pop(f"confirm_exec_{s['id']}", None)
                                st.rerun()
                        with col_n:
                            if st.button("Cancelar", key=f"exec_no_{s['id']}"):
                                st.session_state.pop(f"confirm_exec_{s['id']}", None)
                                st.rerun()
                    delete_key = f"confirm_del_sched_{s['id']}"
                    if cols[5].button("🗑️ Excluir", key=f"del_btn_{s['id']}", width='stretch'):
                        st.session_state[delete_key] = True
                    if st.session_state.get(delete_key):
                        st.warning("Confirmar exclusao?")
                        col_y, col_n = st.columns(2)
                        with col_y:
                            if st.button("Sim, excluir", key=f"del_yes_{s['id']}"):
                                try:
                                    delete_schedule(s["id"])
                                    st.toast(f"Agendamento '{s['name']}' excluído!")
                                    st.session_state.pop(delete_key, None)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao excluir: {e}")
                        with col_n:
                            if st.button("Cancelar", key=f"del_no_{s['id']}"):
                                st.session_state.pop(delete_key, None)
                                st.rerun()

    with tab_manutencao:
        _render_scraper_maintenance(client)


def _build_report_html(ingredient: str, days: int, prices: list) -> str:
    hoje = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    sorted_prices = sorted(prices, key=lambda x: (
        (x.get("normalized") or {}).get("price_per_kg", 999999)
    ))
    rows = ""
    for p in sorted_prices[:50]:
        store = html.escape(p.get("store_name", "?"))
        product = html.escape(p.get("raw_product", "?")[:50])
        price = float(p.get("raw_price", 0))
        unit = html.escape(p.get("raw_unit", ""))
        ppk = ""
        if isinstance(p.get("normalized"), dict):
            ppk = p["normalized"].get("price_per_kg", 0)
            ppk = f"R$ {ppk:.2f}/kg" if ppk else ""
        promo = " 🏷️" if p.get("is_promotion") else ""
        valid = html.escape(p.get("valid_until", ""))
        valid_str = f" (ate {valid})" if valid else ""
        rows += f"<tr><td>{store}{promo}</td><td>{product}</td><td>R$ {price:.2f} {unit}</td><td>{ppk}</td><td>{valid_str}</td></tr>"
    return f"""<html><body style="font-family:Nunito,sans-serif;background:#FFF9F5;padding:20px;">
<h2 style="color:#F59E42;">CustoDoce - Relatorio de Precos</h2>
<p style="color:#8B7355;">{ingredient} - Ultimos {days} dias - {hoje}</p>
<table style="width:100%;border-collapse:collapse;background:#FFF;border-radius:10px;overflow:hidden;">
<tr style="background:#F59E42;color:#FFF;"><th>Loja</th><th>Produto</th><th>Preco</th><th>R$/kg</th><th>Validade</th></tr>
{rows}</table>
<p style="color:#9CA3AF;font-size:0.8rem;margin-top:20px;">Gerado automaticamente pelo CustoDoce em {hoje}</p>
</body></html>"""


def _test_smtp(host: str, port: int, user: str, password: str, to_email: str, from_addr: str = ""):
    import smtplib
    from email.mime.text import MIMEText
    try:
        from_addr = from_addr or user
        msg = MIMEText("Teste de conexao SMTP - CustoDoce\n\nSe voce recebeu este email, o SMTP esta funcionando!", _charset="utf-8")
        msg["Subject"] = "🔧 Teste SMTP CustoDoce"
        msg["From"] = f"CustoDoce <{from_addr}>"
        msg["To"] = to_email
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True, "Email de teste enviado com sucesso!"
    except Exception as e:
        return False, str(e)


def _test_telegram(token: str, chat_id: str):
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "🔧 Teste CustoDoce - Conexao Telegram OK!"},
            timeout=15,
        )
        if resp.status_code == 200:
            return True, "Mensagem de teste enviada com sucesso!"
        return False, f"Erro Telegram {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, str(e)


def tab_relatorios():
    section_title("Relatorios", "Geracao e envio de relatorios de precos")
    st.markdown("### Montar Relatorio de Precos")
    ingredients = load_ingredients()
    options = [i["canonical"] for i in ingredients]
    selected = st.selectbox("Ingrediente", options)
    col1, col2, col3 = st.columns(3)
    with col1:
        days = st.selectbox("Periodo", [7, 15, 30, 60], index=1)
    with col2:
        limit = st.number_input("Produtos", 5, 50, 20)
    with col3:
        pass  # reservado

    if st.button("Gerar Preview", type="primary", width='stretch'):
        prices = _cached_get_price_history(selected, days=days)
        if prices:
            html = _build_report_html(selected, days, prices[:limit])
            st.markdown("### Preview do Relatorio")
            st.components.v1.html(html, height=500, scrolling=True)
            st.markdown("### Enviar por Email")
            smtp_from = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or os.environ.get("GMAIL_USER", "")
            to_email = os.environ.get("ALERT_EMAIL_TO", "")
            send_disabled = not (smtp_from and to_email)
            if st.button(
                "Enviar Relatorio Agora",
                key="send_report",
                width='stretch',
                disabled=send_disabled,
                help="Configure SMTP nas secrets primeiro" if send_disabled else "Enviar relatorio por email",
            ) and not st.session_state.get("confirm_send_report"):
                st.session_state.confirm_send_report = True
                st.rerun()
            if st.session_state.get("confirm_send_report"):
                st.warning(f"Confirma envio para {to_email}?")
                col_y, col_n = st.columns(2)
                with col_y:
                    if st.button("Sim, enviar", key="send_yes"):
                        try:
                            from services.email_service import send_daily_report
                            send_daily_report(report_html=html, to_email=to_email,
                                              subject=f"📊 Relatorio {selected} - {days}d")
                            st.success("Relatorio enviado com sucesso!")
                        except Exception as e:
                            st.error(f"Erro ao enviar: {e}")
                        st.session_state.pop("confirm_send_report", None)
                        st.rerun()
                with col_n:
                    if st.button("Cancelar", key="send_no"):
                        st.session_state.pop("confirm_send_report", None)
                        st.rerun()
        else:
            info_box(f"Nenhum dado para '{selected}' no periodo.", "info")


SECRET_GROUPS = {
    "Supabase": ["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"],
    "Autenticacao": ["AUTH_SECRET_KEY", "ADMIN_PASSWORD_HASH", "TOTP_SECRET", "TOTP_ENABLED"],
    "Telegram": ["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"],
    "Email": ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "GMAIL_USER", "GMAIL_APP_PASSWORD", "ALERT_EMAIL_TO"],
    "GitHub": ["GH_PAT"],
}


def _mask_val(v):
    if not v:
        return "Nao configurado"
    if len(v) > 8:
        return v[:4] + "*" * (len(v) - 8) + v[-4:]
    return v


def _render_admin_account():
    """Secao de conta do administrador dentro da Config."""
    st.markdown("### Conta de Administrador")
    st.markdown("---")

    pw_hash = os.environ.get("ADMIN_PASSWORD_HASH", "")
    pw_plain = os.environ.get("ADMIN_PASSWORD", "")
    totp_enabled = os.environ.get("TOTP_ENABLED", "")
    has_password = bool(pw_hash or pw_plain)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f'Senha: {"✅ Configurada" if has_password else "⚠️ Usando padrao"}'
        )
    with c2:
        st.markdown(
            f'2FA: {"✅ Ativado" if totp_enabled else "❌ Desativado"}'
        )

    tab_senha, tab_totp = st.tabs(["Alterar Senha", "Configurar 2FA"])

    with tab_senha:
        st.markdown("### Conta Admin")
        nova = st.text_input(
            "Nova senha",
            type="password",
            placeholder="Minimo 8 caracteres",
            key="adm_new_pass",
            label_visibility="collapsed",
        )
        confirm = st.text_input(
            "Confirmar senha",
            type="password",
            placeholder="Repita a senha",
            key="adm_confirm_pass",
            label_visibility="collapsed",
        )
        if st.button("Gerar Hash", type="primary", width='stretch'):
            if not nova or len(nova) < 8:
                st.error("Minimo 8 caracteres.")
            elif nova != confirm:
                st.error("Senhas nao conferem.")
            else:
                h = _hash_pw(nova)
                st.success("Hash gerado! Adicione ao Streamlit Secrets:")
                st.code(f"ADMIN_PASSWORD_HASH={h}", language="bash")
                st.info(
                    "Remova a variavel ADMIN_PASSWORD se existir. "
                    "Apos adicionar, reinicie o app."
                )

    with tab_totp:
        st.markdown(
            "Use Google Authenticator, Authy ou similar para escanear o codigo."
        )
        if st.button("Gerar Nova Chave 2FA", width='stretch'):
            secret = _gen_totp()
            uri = _get_totp_uri(secret)
            st.session_state["_setup_totp_secret"] = secret
            st.code(uri, language="text")
            st.markdown(
                f'<p style="font-size:0.85rem;">'
                f"Ou digite manualmente: <strong>{secret}</strong></p>",
                unsafe_allow_html=True,
            )
            st.markdown("### Autenticacao de Dois Fatores")
            teste = st.text_input(
                "Digite o codigo do app para confirmar",
                max_chars=6,
                placeholder="000000",
                key="adm_totp_test",
                label_visibility="collapsed",
            )
            if teste and len(teste) == 6 and _verify_totp(secret, teste):
                st.success("2FA funcionando! Adicione ao Streamlit Secrets:")
                st.code(
                    f"TOTP_SECRET={secret}\nTOTP_ENABLED=1",
                    language="bash",
                )
                st.info("Apos adicionar, reinicie o app.")
        if "adm_totp_test" in st.session_state and st.session_state["adm_totp_test"]:
            stored = st.session_state.get("_setup_totp_secret", "")
            if stored and _verify_totp(stored, st.session_state["adm_totp_test"]):
                st.success("2FA verificado!")

    st.markdown("---")


def tab_config():
    section_title("Configuracao", "Configuracoes do sistema")
    _render_admin_account()
    tab_env, tab_ing, tab_stores, tab_features = st.tabs(
        ["Variaveis de Ambiente", "Ingredientes", "Lojas", "Features"]
    )

    with tab_env:
        st.markdown("### Configuracao SMTP (envio de relatorios)")
        st.markdown(
            '<p style="font-size:0.85rem;opacity:0.7;margin-bottom:1rem;">'
            "SMTP_HOST e SMTP_PORT sao as configuracoes do provedor. "
            "Para Gmail: smtp.gmail.com:587 | SendGrid: smtp.sendgrid.net:587 | Brevo: smtp-relay.brevo.com:587"
            "</p>",
            unsafe_allow_html=True,
        )
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            env_host = st.text_input(
                "SMTP_HOST",
                value=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
                key="env_smtp_host",
                help="Servidor SMTP do provedor",
            )
            env_user = st.text_input(
                "SMTP_USER (email do remetente)",
                value=os.environ.get("SMTP_USER", ""),
                key="env_smtp_user",
                help="Email cadastrado no provedor SMTP",
            )
        with col_m2:
            env_port = st.text_input(
                "SMTP_PORT",
                value=os.environ.get("SMTP_PORT", "587"),
                key="env_smtp_port",
                help="Porta do servidor SMTP (587 TLS ou 465 SSL)",
            )
            env_pass = st.text_input(
                "SMTP_PASSWORD (senha ou API Key)",
                value=os.environ.get("SMTP_PASSWORD", ""),
                type="password",
                key="env_smtp_pass",
                help="Senha do email ou API Key do provedor",
            )
        with col_m3:
            env_from = st.text_input(
                "SMTP_FROM (opcional)",
                value=os.environ.get("SMTP_FROM", ""),
                key="env_smtp_from",
                help="Email do remetente (se diferente de SMTP_USER)",
            )
            env_to = st.text_input(
                "ALERT_EMAIL_TO (email destino)",
                value=os.environ.get("ALERT_EMAIL_TO", ""),
                key="env_smtp_to",
                help="Para qual email os relatorios serao enviados",
            )
        if env_user and env_pass and env_to and st.button("Testar Envio de Email", key="test_email_cfg", width='stretch'):
                ok, msg = _test_smtp(env_host, int(env_port or "587"), env_user, env_pass, env_to, env_from)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

        st.markdown("---")
        st.markdown("### Configuracao do Telegram")
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            env_tg_token = st.text_input(
                "TELEGRAM_TOKEN",
                value=os.environ.get("TELEGRAM_TOKEN", ""),
                type="password",
                key="env_tg_token",
                help="Token do bot (ex: 123456:ABC-DEF1234...) - obtenha com @BotFather",
            )
        with col_t2:
            env_tg_chat = st.text_input(
                "TELEGRAM_CHAT_ID",
                value=os.environ.get("TELEGRAM_CHAT_ID", ""),
                key="env_tg_chat",
                help="Seu ID numerico do Telegram - obtenha com @userinfobot",
            )
        if env_tg_token and env_tg_chat and st.button("Testar Envio Telegram", key="test_tg_cfg", width='stretch'):
                ok, msg = _test_telegram(env_tg_token, env_tg_chat)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

        st.markdown("---")
        st.markdown(
            '<p style="font-size:0.85rem;opacity:0.7;margin-bottom:1rem;">'
            "Edite as variaveis de ambiente. As alteracoes sao salvas no arquivo .env "
            "(valem na proxima execucao).</p>",
            unsafe_allow_html=True,
        )

        if "edit_mode" not in st.session_state:
            st.session_state.edit_mode = False

        col1, col2 = st.columns([1, 5])
        with col1:
            toggle_label = "Desativar Edicao" if st.session_state.edit_mode else "Ativar Edicao"
            if st.button(toggle_label, width='stretch'):
                st.session_state.edit_mode = not st.session_state.edit_mode
                st.rerun()

        for group, keys in SECRET_GROUPS.items():
            with st.expander(f"**{group}** ({len(keys)} variaveis)", expanded=False):
                for k in keys:
                    current = os.environ.get(k, "")
                    if st.session_state.edit_mode:
                        new_val = st.text_input(
                            k,
                            value=current,
                            key=f"env_{k}",
                            type="password" if "KEY" in k or "TOKEN" in k or "PASSWORD" in k or "SECRET" in k else "default",
                        )
                    else:
                        st.markdown(
                            f'<div style="display:flex;justify-content:space-between;'
                            f'padding:0.25rem 0;border-bottom:1px solid #F0E6DB;">'
                            f'<span style="font-weight:600;">{k}</span>'
                            f'<span style="font-family:monospace;color:#8B7355;">{_mask_val(current)}</span>'
                            f"</div>",
                            unsafe_allow_html=True,
                        )

        if st.session_state.edit_mode:
            st.markdown("---")
            if st.button("Salvar todas as alteracoes", type="primary", width='stretch'):
                all_keys = [k for ks in SECRET_GROUPS.values() for k in ks]
                lines = []
                env_path = ".env"
                try:
                    with open(env_path, encoding="utf-8") as f:
                        lines = f.readlines()
                except FileNotFoundError:
                    pass
                existing_keys = dict.fromkeys(all_keys, False)
                new_lines = []
                for line in lines:
                    stripped = line.strip()
                    if stripped and "=" in stripped:
                        ek = stripped.split("=", 1)[0].strip()
                        if ek in existing_keys:
                            new_val = st.session_state.get(f"env_{ek}", os.environ.get(ek, ""))
                            new_lines.append(f'{ek}="{new_val}"\n')
                            existing_keys[ek] = True
                        else:
                            new_lines.append(line)
                    else:
                        new_lines.append(line)
                for k, found in existing_keys.items():
                    if not found:
                        new_val = st.session_state.get(f"env_{k}", os.environ.get(k, ""))
                        new_lines.append(f'{k}="{new_val}"\n')
                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                for k in all_keys:
                    os.environ[k] = st.session_state.get(f"env_{k}", os.environ.get(k, ""))
                st.success("Configuracoes salvas e aplicadas imediatamente!")

    with tab_ing:
        st.markdown("**Ingredientes (ingredients.yaml)**")
        ingredients = load_ingredients()
        st.code(yaml.dump({"ingredients": ingredients}), language="yaml")

    with tab_stores:
        st.markdown("**Lojas (stores.yaml)**")
        try:
            with open("config/stores.yaml", encoding="utf-8") as f:
                stores_data = yaml.safe_load(f)
            st.code(yaml.dump(stores_data), language="yaml")
        except FileNotFoundError:
            info_box("Arquivo nao encontrado", "error")

    with tab_features:
        st.markdown("**Features (config/features.yaml)**")
        st.markdown(
            '<p style="font-size:0.85rem;opacity:0.7;margin-bottom:1rem;">'
            "Edite este arquivo para ligar/desligar funcionalidades sem alterar codigo.</p>",
            unsafe_allow_html=True,
        )
        try:
            feat_path = os.path.join(os.path.dirname(__file__), "..", "config", "features.yaml")
            with open(feat_path, encoding="utf-8") as f:
                feat_data = yaml.safe_load(f)
            st.code(yaml.dump(feat_data), language="yaml")
            if st.button("Recarregar Configuracoes", width='stretch'):
                reload_config()
                st.success("Configuracoes recarregadas do arquivo!")
        except FileNotFoundError:
            info_box("Arquivo features.yaml nao encontrado", "error")


def _run_service_test(label, fn):
    with st.status(f"Testando {label}...", expanded=False) as status:
        start = datetime.now()
        try:
            msg = fn()
            elapsed = (datetime.now() - start).total_seconds()
            status.update(
                label=f"{label} — OK ({elapsed:.2f}s)",
                state="complete",
            )
            return ("OK", f"{msg} ({elapsed:.2f}s)")
        except Exception as e:
            elapsed = (datetime.now() - start).total_seconds()
            status.update(
                label=f"{label} — ERRO ({elapsed:.2f}s)",
                state="error",
            )
            return ("ERRO", str(e))


def _test_supabase():
    from services.supabase_client import get_supabase as gs
    client = gs()
    resp = client.table("prices").select("count", count="exact").limit(1).execute()
    return f"Tabela prices acessivel (count={resp.count})"


def _test_yaml(path):
    with open(path, encoding="utf-8") as f:
        yaml.safe_load(f)
    return f"{path} valido"


def _test_auth():
    from services.auth import hash_password, verify_password
    h = hash_password("test")
    if not verify_password("test", h):
        raise ValueError("Falha na verificacao de senha")
    return "PBKDF2-HMAC-SHA256 600k iter"


def _test_rate_limiter():
    from services.rate_limiter import RateLimiter
    rl = RateLimiter()
    if rl.is_limited("test_key"):
        raise ValueError("Rate limiter retornou limitado indevidamente")
    return "SQLite + cache memoria"


def _test_env_var(key):
    v = os.environ.get(key)
    if v:
        return f"{key} configurado ({len(v)} chars)"
    raise ValueError(f"{key} nao configurado")


def tab_diagnostico():
    section_title("Diagnostico", "Health check completo do sistema")

    tests = [
        ("Supabase", lambda: _test_supabase()),
        ("ingredients.yaml", lambda: _test_yaml("config/ingredients.yaml")),
        ("stores.yaml", lambda: _test_yaml("config/stores.yaml")),
        ("Auth (PBKDF2)", _test_auth),
        ("Rate Limiter", _test_rate_limiter),
        ("Python", lambda: __import__("sys").version),
    ]

    for svc in ["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY",
                "AUTH_SECRET_KEY", "TELEGRAM_TOKEN", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD",
                "GMAIL_USER", "GMAIL_APP_PASSWORD",
                "GH_PAT"]:
        tests.append((f"ENV: {svc}", lambda k=svc: _test_env_var(k)))

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Executar Todos os Testes", type="primary", width='stretch'):
            for label, fn in tests:
                key = f"diag_{label.replace(' ','_').replace('(','').replace(')','').replace(':','')}"
                st.session_state[key] = _run_service_test(label, fn)
            st.rerun()
    with col2:
        clear = st.button("Limpar Resultados", width='stretch')
        if clear:
            for k in list(st.session_state.keys()):
                if k.startswith("diag_"):
                    del st.session_state[k]

    st.markdown("---")
    st.markdown("### Testes Individuais")

    for label, fn in tests:
        key = f"diag_{label.replace(' ','_').replace('(','').replace(')','').replace(':','')}"
        result = st.session_state.get(key)
        with st.expander(f"{label} {'✅' if result and result[0]=='OK' else '❌' if result else '⏳'}", expanded=False):
            status_placeholder = st.empty()
            if st.button("Testar", key=f"btn_{key}", width='stretch'):
                st.session_state[key] = _run_service_test(label, fn)
                st.rerun()
            if result:
                icon = "✅" if result[0] == "OK" else "❌"
                color = "#10B981" if result[0] == "OK" else "#EF4444"
                status_placeholder.markdown(
                    f'<div style="padding:0.5rem 1rem;border-radius:8px;'
                    f'background:{color}15;border:1px solid {color}40;">'
                    f'<strong style="color:{color};">{icon} {result[0]}</strong>'
                    f'<br/><span style="font-size:0.85rem;">{result[1]}</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")
    st.markdown("### Testes de Comunicacao")

    with st.expander("📧  Testar SMTP", expanded=False):
        if not get_config("features.email.enabled", True):
            info_box("Email desabilitado em config/features.yaml", "warning")
        else:
            smtp_host = os.environ.get("SMTP_HOST", "")
            smtp_port = os.environ.get("SMTP_PORT", "")
            smtp_user = os.environ.get("SMTP_USER", "") or os.environ.get("GMAIL_USER", "")
            smtp_pass = os.environ.get("SMTP_PASSWORD", "") or os.environ.get("GMAIL_APP_PASSWORD", "")
            smtp_from = os.environ.get("SMTP_FROM", "")
            email_to = os.environ.get("ALERT_EMAIL_TO", "")
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("SMTP_HOST", value=smtp_host, key="diag_smtp_host")
                st.text_input("SMTP_PORT", value=smtp_port, key="diag_smtp_port")
                st.text_input("SMTP_USER", value=smtp_user, key="diag_smtp_user")
            with col2:
                st.text_input("SMTP_PASSWORD", value=smtp_pass, type="password", key="diag_smtp_pass")
                st.text_input("SMTP_FROM", value=smtp_from, key="diag_smtp_from")
                st.text_input("ALERT_EMAIL_TO", value=email_to, key="diag_smtp_to")
            if st.button("Enviar Email de Teste", key="diag_btn_smtp", width='stretch'):
                try:
                    import smtplib
                    from email.message import EmailMessage
                    msg = EmailMessage()
                    msg.set_content("Teste de envio CustoDoce - " + datetime.now().isoformat())
                    msg["Subject"] = "CustoDoce - Teste SMTP"
                    msg["From"] = f"CustoDoce <{smtp_from or smtp_user}>"
                    msg["To"] = email_to
                    with smtplib.SMTP(smtp_host or "smtp.gmail.com", int(smtp_port or "587"), timeout=15) as server:
                        server.ehlo()
                        server.starttls()
                        server.login(smtp_user, smtp_pass)
                        server.send_message(msg)
                    st.success(f"Email enviado para {email_to}")
                except Exception as e:
                    st.error(f"Falha: {e}")

    with st.expander("🤖  Testar Telegram", expanded=False):
        if not get_config("features.telegram.enabled", True):
            info_box("Telegram desabilitado em config/features.yaml", "warning")
        else:
            tg_token = os.environ.get("TELEGRAM_TOKEN", "")
            tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
            col1, col2 = st.columns(2)
            with col1:
                tg_token_inp = st.text_input("TELEGRAM_TOKEN", value=tg_token, type="password", key="diag_tg_token")
            with col2:
                tg_chat_inp = st.text_input("TELEGRAM_CHAT_ID", value=tg_chat, key="diag_tg_chat")
            if st.button("Enviar Mensagem de Teste", key="diag_btn_telegram", width='stretch'):
                try:
                    resp = httpx.post(
                        f"https://api.telegram.org/bot{tg_token_inp}/sendMessage",
                        json={"chat_id": tg_chat_inp, "text": f"Teste CustoDoce - {datetime.now().isoformat()}"},
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        st.success(f"Mensagem enviada para chat {tg_chat_inp}")
                    else:
                        st.error(f"Erro {resp.status_code}: {resp.text}")
                except Exception as e:
                    st.error(f"Falha: {e}")


# ============================================================
# NOVAS TABS: AGENDAMENTOS, FREQUENCIAS, ALERTAS
# ============================================================




def tab_alertas():
    section_title("Alertas e Notificações")
    st.caption("Configure destinatários e regras de disparo (email, telegram, whatsapp).")

    tab_dest, tab_rules = st.tabs(["📬 Destinatários", "⚙️ Regras"])

    with tab_dest:
        recipients = _cached_get_all_recipients(include_inactive=True)
        if recipients:
            df = pd.DataFrame(recipients)
            df["active"] = df["active"].map({True: "✅", False: "⏸️"})
            st.dataframe(_pt_cols(df[["channel", "target", "name", "active"]]), width='stretch', hide_index=True)
        else:
            info_box("Nenhum destinatario cadastrado.", "info")

        with st.expander("➕  Novo Destinatário", expanded=False), st.form("form_recipient"):
            col1, col2 = st.columns(2)
            with col1:
                channel = st.selectbox("Canal", ["email", "telegram", "whatsapp"], format_func=lambda x: {"email": "Email", "telegram": "Telegram", "whatsapp": "WhatsApp"}.get(x, x))
                target = st.text_input("Destino", placeholder="email@dominio.com ou -1001234567890")
            with col2:
                name = st.text_input("Nome (opcional)", placeholder="Financeiro, Gestor, etc")
                active = st.checkbox("Ativo", value=True)
            if st.form_submit_button("Salvar", width='stretch'):
                try:
                    upsert_recipient({"channel": channel, "target": target, "name": name, "active": active})
                    st.toast("Destinatário salvo!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar destinatário: {e}")

        if recipients:
            with st.expander("✏️  Editar / Excluir", expanded=False):
                for r in recipients:
                    cols = st.columns([2, 3, 2, 1, 1])
                    cols[0].write(r["channel"])
                    cols[1].write(r["target"])
                    cols[2].write(r["name"] or "—")
                    if cols[3].button("Editar", key=f"edit_rec_{r['id']}", width='stretch'):
                        st.session_state[f"editing_rec_{r['id']}"] = True
                        st.rerun()
                    delete_key = f"confirm_del_rec_{r['id']}"
                    if cols[4].button("🗑️ Excluir", key=f"del_btn_rec_{r['id']}", width='stretch'):
                        st.session_state[delete_key] = True
                    if st.session_state.get(delete_key):
                        st.warning("Confirmar exclusao?")
                        col_y, col_n = st.columns(2)
                        with col_y:
                            if st.button("Sim, excluir", key=f"del_yes_rec_{r['id']}"):
                                try:
                                    delete_recipient(r["id"])
                                    st.toast("Destinatário excluído!")
                                    st.session_state.pop(delete_key, None)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao excluir: {e}")
                        with col_n:
                            if st.button("Cancelar", key=f"del_no_rec_{r['id']}"):
                                st.session_state.pop(delete_key, None)
                                st.rerun()

    with tab_rules:
        rules = _cached_get_all_alert_rules(include_disabled=True)
        if rules:
            df = pd.DataFrame(rules)
            df["enabled"] = df["enabled"].map({True: "✅", False: "⏸️"})
            st.dataframe(_pt_cols(df[["name", "channel", "trigger", "frequency_minutes", "enabled"]]), width='stretch', hide_index=True)
        else:
            info_box("Nenhuma regra de alerta configurada.", "info")

        with st.expander("➕  Nova Regra", expanded=False), st.form("form_rule"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Nome da Regra", placeholder="ex: Alerta Queda Preço Leite Condensado")
                channel = st.selectbox("Canal", ["email", "telegram", "whatsapp"], format_func=lambda x: {"email": "Email", "telegram": "Telegram", "whatsapp": "WhatsApp"}.get(x, x))
                trigger = st.selectbox("Gatilho", ["price_drop", "new_low_price", "daily_report", "scrape_failure", "review_queue_threshold"], format_func=lambda x: {"price_drop": "Queda de Preço", "new_low_price": "Menor Preço Histórico", "daily_report": "Relatório Diário", "scrape_failure": "Falha no Scraper", "review_queue_threshold": "Fila de Revisão"}.get(x, x))
            with col2:
                freq = st.number_input("Anti-spam (minutos)", min_value=60, value=1440, step=60)
                recipients_list = get_active_recipients(channel)
                recipient_ids = st.multiselect("Destinatários", options=[r["id"] for r in recipients_list], format_func=lambda x: next((r["target"] for r in recipients_list if r["id"] == x), x))
                enabled = st.checkbox("Ativo", value=True)
                condition = st.text_area("Condição JSON", value='{"threshold_pct": 10}', height=80)
                if condition and condition.strip():
                    try:
                        parsed = json.loads(condition)
                        st.caption(f"JSON valido: {json.dumps(parsed, indent=2)[:200]}")
                    except json.JSONDecodeError as e:
                        st.caption(f"JSON invalido: {e}")
                template = st.text_area("Template Jinja2 (opcional)", placeholder="{{ ingredient }} caiu para {{ price }}", height=80)
                if st.form_submit_button("Salvar", width='stretch'):
                    try:
                        upsert_alert_rule({

                            "name": name,
                            "channel": channel,
                            "trigger": trigger,
                            "condition": json.loads(condition) if condition else {},
                            "frequency_minutes": freq,
                            "recipients": recipient_ids,
                            "template": template or None,
                            "enabled": enabled,
                        })
                        st.toast("Regra salva!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar regra: {e}")


# ═══════════════════════════════════════════════════════════════
# TAB: FONTES & OFERTAS
# ═══════════════════════════════════════════════════════════════

def tab_fontes():
    section_title("Fontes & Ofertas", "Quais lojas tem quais ingredientes e promocoes ativas")
    valid_only = _valid_only_toggle()
    ingredients = load_ingredients()
    ing_options = [i["canonical"] for i in ingredients]

    tab_foco, tab_promos, tab_ranking_fontes = st.tabs(["Cobertura por Ingrediente", "Promocoes Ativas", "Ranking de Fontes"])

    with tab_foco:
        selected = st.selectbox("Ingrediente", ing_options, key="fontes_ing")
        tier_filter = st.multiselect("Tier", [1, 2, 3, 4], default=[1, 2, 3], key="fontes_tier")
        if st.button("Buscar Fontes", type="primary", key="btn_fontes"):
            with st.spinner("Buscando precos..."):
                prices = search_prices(selected, valid_only=valid_only, limit=100)
                if not prices:
                    info_box(f"Nenhum preco encontrado para '{selected}'", "info")
                    return
                df = pd.DataFrame(prices)
                df = df[df["tier"].isin(tier_filter)]
                if df.empty:
                    info_box("Nenhum resultado para os tiers selecionados", "warning")
                    return
                df["price_per_kg"] = _get_kg(df)

                agg_cols = {
                    "Precos": ("raw_price", "count"),
                    "Menor_kg": ("price_per_kg", "min"),
                    "Medio_kg": ("price_per_kg", "mean"),
                    "Promocoes": ("is_promotion", "sum"),
                    "Ultima": ("collected_at", "max"),
                }
                if "city" in df.columns:
                    agg_cols["Cidade"] = ("city", lambda x: x.mode().iloc[0] if not x.mode().empty else "")
                src = df.groupby("store_name").agg(**agg_cols).reset_index().sort_values("Menor_kg")

                st.markdown(f"**{len(src)} fontes** para **{selected}**")
                src["Menor_kg"] = src["Menor_kg"].apply(lambda x: f"R$ {x:.2f}")
                src["Medio_kg"] = src["Medio_kg"].apply(lambda x: f"R$ {x:.2f}")
                src["Promocoes"] = src["Promocoes"].astype(int)
                st.dataframe(src.head(100), width='stretch', hide_index=True)

                _export_csv_button(src, f"fontes_{selected}.csv", key="csv_fontes")

    with tab_promos:
        st.markdown("### Ofertas e Promocoes")
        tier_p = st.multiselect("Tier", [1, 2, 3, 4], default=[1, 2, 3], key="promos_tier")
        if st.button("Buscar Promocoes", type="primary", key="btn_promos"):
            with st.spinner("Buscando precos..."):
                all_prices = _cached_get_all_current_prices(valid_only=valid_only)
                if not all_prices:
                    info_box("Nenhum preco disponivel", "info")
                    return
                all_promo = []
                for p in all_prices:
                    if p.get("is_promotion") and p.get("tier") in tier_p:
                        ing = p.get("ingredient_id", "?")
                        all_promo.append({**p, "_ingredient": ing})
                if not all_promo:
                    info_box("Nenhuma promocao ativa encontrada", "info")
                    return
                dfp = pd.DataFrame(all_promo)
                dfp["price_per_kg"] = dfp["normalized"].apply(_format_kg)
                dfp = dfp.sort_values("price_per_kg")
                st.success(f"{len(dfp)} promocoes ativas")
                display_p = dfp[["_ingredient", "store_name", "brand", "raw_product", "raw_price", "raw_unit", "price_per_kg", "valid_until"]].copy()
                display_p["price_per_kg"] = display_p["price_per_kg"].apply(lambda x: f"R$ {x:.2f}" if x > 0 else "—")
                display_p.columns = ["Ingrediente", "Loja", "Marca", "Produto", "Preco", "Unidade", "R$/kg", "Valido ate"]
                st.dataframe(display_p.head(100), width='stretch', hide_index=True)

    with tab_ranking_fontes:
        st.markdown("### Lojas com maior cobertura de ingredientes")
        tier_r = st.multiselect("Tier", [1, 2, 3, 4], default=[1, 2, 3], key="ranking_tier")
        if st.button("Calcular", type="primary", key="btn_ranking"):
            with st.spinner("Buscando precos..."):
                all_prices = _cached_get_all_current_prices(valid_only=valid_only)
                store_coverage = {}
                for p in all_prices:
                    if p.get("tier") in tier_r:
                        s_name = p.get("store_name", "?")
                        ing = p.get("ingredient_id", "?")
                        if s_name not in store_coverage:
                            store_coverage[s_name] = set()
                        store_coverage[s_name].add(ing)
                if not store_coverage:
                    info_box("Nenhum dado disponivel", "info")
                    return
                rank_df = pd.DataFrame([
                    {"Loja": s, "Ingredientes": len(ings), "Cobertura": f"{len(ings)}/{len(ing_options)}"}
                    for s, ings in sorted(store_coverage.items(), key=lambda x: -len(x[1]))
                ])
                st.dataframe(rank_df.head(100), width='stretch', hide_index=True)
                fig_r = px.bar(rank_df.head(15), x="Loja", y="Ingredientes",
                               title="Top 15 lojas por cobertura",
                               color="Ingredientes",
                               color_continuous_scale="Oranges",
                               labels={"Ingredientes": "Ingredientes disponiveis"})
                fig_r.update_layout(showlegend=False)
                st.plotly_chart(fig_r, width='stretch')


# ═══════════════════════════════════════════════════════════════
# TAB: RANKING HISTORICO
# ═══════════════════════════════════════════════════════════════

def tab_ranking():
    section_title("Ranking Historico", "Evolucao do preco por loja ao longo do tempo")
    valid_only = _valid_only_toggle()
    ingredients = load_ingredients()
    options = [i["canonical"] for i in ingredients]
    selected = st.selectbox("Ingrediente", options, key="ranking_sel")

    col1, col2, col3 = st.columns(3)
    with col1:
        days = st.slider("Periodo (dias)", 7, 365, 90, key="ranking_days")
    with col2:
        top_n = st.number_input("Top N lojas", min_value=3, max_value=20, value=10, key="ranking_topn")
    with col3:
        chart_style = st.selectbox("Estilo", ["Linha", "Area", "Barras"], key="ranking_style")

    if st.button("Gerar Ranking", type="primary"):
        with st.spinner("Buscando precos..."):
            history = _cached_get_price_history(selected, days=days, valid_only=valid_only)
            if not history:
                info_box(f"Sem historico para '{selected}' no periodo", "info")
                return
            df = pd.DataFrame(history)
            df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)
            df["price_per_kg"] = df["normalized"].apply(_format_kg)
            df = df[df["price_per_kg"] > 0].copy()

            store_avg = df.groupby("store_name")["price_per_kg"].mean().reset_index()
            top_stores = store_avg.nsmallest(top_n, "price_per_kg")["store_name"].tolist()
            df_top = df[df["store_name"].isin(top_stores)]

            if df_top.empty:
                info_box("Dados insuficientes para o ranking", "warning")
                return

            if chart_style == "Linha":
                fig = px.line(df_top, x="collected_at", y="price_per_kg", color="store_name",
                              title=f"{selected} - Ranking de precos ({days} dias)",
                              labels={"collected_at": "Data", "price_per_kg": "R$/kg", "store_name": "Loja"},
                              color_discrete_sequence=[CD_ORANGE, CD_PINK, CD_BLUE, "#FBBF5E", "#60A5FA", "#C94D78"])
                fig.update_traces(mode="lines+markers")
            elif chart_style == "Area":
                fig = px.area(df_top, x="collected_at", y="price_per_kg", color="store_name",
                              title=f"{selected} - Ranking de precos ({days} dias)",
                              labels={"collected_at": "Data", "price_per_kg": "R$/kg", "store_name": "Loja"},
                              color_discrete_sequence=[CD_ORANGE, CD_PINK, CD_BLUE, "#FBBF5E", "#60A5FA", "#C94D78"])
            else:
                df_agg = df_top.groupby(["collected_at", "store_name"])["price_per_kg"].mean().reset_index()
                fig = px.bar(df_agg, x="collected_at", y="price_per_kg", color="store_name",
                             title=f"{selected} - Barras por loja ({days} dias)",
                             labels={"collected_at": "Data", "price_per_kg": "R$/kg", "store_name": "Loja"},
                             barmode="group",
                             color_discrete_sequence=[CD_ORANGE, CD_PINK, CD_BLUE, "#FBBF5E", "#60A5FA", "#C94D78"])
            st.plotly_chart(fig, width='stretch')

            st.markdown("### Ranking atual (ultima coleta por loja)")
            latest = df_top.sort_values("collected_at").groupby("store_name").last().reset_index()
            latest = latest.sort_values("price_per_kg")
            latest["R$/kg"] = latest["price_per_kg"].apply(lambda x: f"R$ {x:.2f}")
            latest["Ultima coleta"] = latest["collected_at"].dt.strftime("%d/%m/%Y")
            latest["Produto"] = latest["raw_product"]
            latest["Marca"] = latest.get("brand", "")
            rank_display = latest[["store_name", "Marca", "Produto", "R$/kg", "Ultima coleta"]]
            rank_display.columns = ["Loja", "Marca", "Produto", "R$/kg", "Ultima coleta"]
            st.dataframe(rank_display, width='stretch', hide_index=True)

            st.markdown("### Estatisticas do periodo")
            stats = df_top.groupby("store_name").agg(
                Media=("price_per_kg", "mean"),
                Minimo=("price_per_kg", "min"),
                Maximo=("price_per_kg", "max"),
                Coletas=("price_per_kg", "count"),
            ).reset_index().sort_values("Media")
            stats["Media"] = stats["Media"].apply(lambda x: f"R$ {x:.2f}")
            stats["Minimo"] = stats["Minimo"].apply(lambda x: f"R$ {x:.2f}")
            stats["Maximo"] = stats["Maximo"].apply(lambda x: f"R$ {x:.2f}")
            stats.columns = ["Loja", "Media", "Minimo", "Maximo", "Coletas"]
            st.dataframe(stats, width='stretch', hide_index=True)

            _export_csv_button(
                stats,
                f"ranking_{selected}_{pd.Timestamp.utcnow().strftime('%Y%m%d')}.csv",
                "Exportar Estatisticas CSV",
                key="csv_ranking",
            )


# ═══════════════════════════════════════════════════════════════
# TAB: INSIGHTS
# ═══════════════════════════════════════════════════════════════

def tab_insights():
    section_title("Insights Produto x Loja", "Heatmap, outliers, vencedores historicos, tendencias e melhores ofertas")
    valid_only = _valid_only_toggle()
    ingredients = load_ingredients()
    ing_options = [i["canonical"] for i in ingredients] if ingredients else []

    tab_heatmap, tab_outliers, tab_melhores, tab_vencedores, tab_tendencias, tab_cross = st.tabs([
        "Heatmap Precos", "Outliers", "Melhores Ofertas",
        "Vencedores Historicos", "Tendencias", "Ranking Cross-Ingredient"
    ])

    with tab_heatmap:
        st.markdown("### Comparacao de precos entre lojas e ingredientes")
        tier_h = st.multiselect("Tier", [1, 2, 3, 4], default=[1, 2], key="heatmap_tier")
        limit_ing = st.number_input("Max ingredientes", min_value=3, max_value=20, value=10, key="heatmap_lim")
        if st.button("Gerar Heatmap", type="primary", key="btn_heatmap"):
            with st.spinner("Buscando precos..."):
                all_prices = _cached_get_all_current_prices(valid_only=valid_only)
                target_ings = set(ing_options[:limit_ing])
                rows = []
                for p in all_prices:
                    ing = p.get("ingredient_id", "")
                    if ing not in target_ings:
                        continue
                    if p.get("tier") in tier_h:
                        n = p.get("normalized") or {}
                        rows.append({"ingrediente": ing, "loja": p.get("store_name", "?"),
                                     "price_per_kg": n.get("price_per_kg", 0) or 0})
                if not rows:
                    info_box("Sem dados para o heatmap", "info")
                    return
                dfh = pd.DataFrame(rows)
                dfh = dfh[dfh["price_per_kg"] > 0]
                if dfh.empty:
                    info_box("Sem precos validos para o heatmap", "warning")
                    return
                heat = dfh.groupby(["ingrediente", "loja"])["price_per_kg"].mean().reset_index()
                pivot = heat.pivot(index="ingrediente", columns="loja", values="price_per_kg")
                fig = px.imshow(pivot, text_auto=".2f", aspect="auto",
                                title="Preco medio por kg — Ingrediente vs Loja",
                                color_continuous_scale="YlOrRd",
                                labels={"x": "Loja", "y": "Ingrediente", "color": "R$/kg"})
                fig.update_layout(height=max(400, len(pivot) * 40))
                st.plotly_chart(fig, width='stretch')

    with tab_outliers:
        st.markdown("### Precos destoantes (acima ou abaixo da media)")
        tier_o = st.multiselect("Tier", [1, 2, 3, 4], default=[1, 2], key="outlier_tier")
        threshold = st.slider("Desvio padrao", 1.0, 3.0, 2.0, 0.25, key="outlier_threshold")
        if st.button("Detectar Outliers", type="primary", key="btn_outliers"):
            with st.spinner("Buscando precos..."):
                all_prices = _cached_get_all_current_prices(valid_only=valid_only)
                out_rows = []
                from collections import defaultdict
                by_ing = defaultdict(list)
                for p in all_prices:
                    if p.get("tier") in tier_o:
                        n = p.get("normalized") or {}
                        by_ing[p.get("ingredient_id", "?")].append({
                            "store": p.get("store_name", "?"),
                            "product": p.get("raw_product", ""),
                            "price": n.get("price_per_kg", 0) or 0,
                            "raw_price": p.get("raw_price", 0),
                            "raw_unit": p.get("raw_unit", ""),
                        })
                for ing, vals in by_ing.items():
                    if len(vals) >= 3:
                        valid_vals = [v for v in vals if v["price"] > 0]
                        if not valid_vals:
                            continue
                        prices_list = [v["price"] for v in valid_vals]
                        avg = statistics.mean(prices_list)
                        std = statistics.stdev(prices_list) if len(prices_list) > 1 else 0
                        for v in valid_vals:
                            if std > 0 and abs(v["price"] - avg) / std >= threshold:
                                out_rows.append({**v, "ingrediente": ing, "media": avg, "desvio": std})
                if not out_rows:
                    info_box("Nenhum outlier detectado com esse threshold", "success")
                    return
                dfo = pd.DataFrame(out_rows)
                dfo["z_score"] = abs(dfo["price"] - dfo["media"]) / dfo["desvio"]
                dfo = dfo.sort_values("z_score", ascending=False)
                st.warning(f"{len(dfo)} outlier(s) detectado(s)")
                dfo["price"] = dfo["price"].apply(lambda x: f"R$ {x:.2f}")
                dfo["media"] = dfo["media"].apply(lambda x: f"R$ {x:.2f}")
                display_o = dfo[["ingrediente", "store", "product", "price", "media", "z_score"]].copy()
                display_o.columns = ["Ingrediente", "Loja", "Produto", "Preco", "Media", "Z-Score"]
                st.dataframe(display_o.head(100), width='stretch', hide_index=True)

    with tab_melhores:
        st.markdown("### Melhores ofertas do momento")
        tier_m = st.multiselect("Tier", [1, 2, 3, 4], default=[1, 2], key="melhores_tier")
        top_m = st.number_input("Top por ingrediente", min_value=1, max_value=10, value=3, key="melhores_top")
        if st.button("Encontrar Melhores", type="primary", key="btn_melhores"):
            with st.spinner("Buscando precos..."):
                all_prices = _cached_get_all_current_prices(valid_only=valid_only)
                from collections import defaultdict
                by_ing = defaultdict(list)
                for p in all_prices:
                    if p.get("tier") in tier_m:
                        n = p.get("normalized") or {}
                        p["_price_kg"] = n.get("price_per_kg", 0) or 0
                        by_ing[p.get("ingredient_id", "?")].append(p)
                best_rows = []
                for ing, pp in by_ing.items():
                    pp.sort(key=lambda x: x["_price_kg"])
                    for p in pp[:top_m]:
                        brand = p.get("brand", "")
                        best_rows.append({
                            "ingrediente": ing,
                            "loja": p.get("store_name", "?"),
                            "marca": brand,
                            "produto": p.get("raw_product", ""),
                            "preco": p.get("raw_price", 0),
                            "unidade": p.get("raw_unit", ""),
                            "R$/kg": p["_price_kg"],
                            "promocao": p.get("is_promotion", False),
                            "validade": p.get("valid_until", ""),
                        })
                if not best_rows:
                    info_box("Nenhuma oferta encontrada", "info")
                    return
                dfb = pd.DataFrame(best_rows)
                dfb = dfb.sort_values(["ingrediente", "R$/kg"])
                st.success(f"{len(dfb)} ofertas encontradas")
                dfb["R$/kg"] = dfb["R$/kg"].apply(lambda x: f"R$ {x:.2f}" if x > 0 else "—")
                dfb["preco"] = dfb.apply(lambda r: f"R$ {r['preco']:.2f} {r['unidade']}", axis=1)
                display_b = dfb[["ingrediente", "loja", "marca", "produto", "preco", "R$/kg", "promocao", "validade"]].copy()
                display_b.columns = ["Ingrediente", "Loja", "Marca", "Produto", "Preco", "R$/kg", "Promocao", "Validade"]
                st.dataframe(display_b.head(100), width='stretch', hide_index=True)

                _export_csv_button(display_b,
                    f"melhores_ofertas_{pd.Timestamp.utcnow().strftime('%Y%m%d')}.csv",
                    "Exportar Ofertas CSV", key="csv_melhores")

    with tab_vencedores:
        st.markdown("### Lojas que mais vezes foram a mais barata")
        st.caption("Contagem de dias em que cada loja teve o menor price_per_kg por ingrediente nos ultimos 90 dias.")
        if st.button("Calcular Vencedores", type="primary", key="btn_vencedores"):
            with st.spinner("Buscando precos..."):
                winners = get_longitudinal_winners(days=90)
                if not winners:
                    info_box("Sem dados historicos suficientes", "info")
                else:
                    df_w = pd.DataFrame(winners)
                    st.success(f"{df_w['ingredient_id'].nunique()} ingredientes, {df_w['store_name'].nunique()} lojas")
                    fig_w = px.bar(df_w.head(20), x="store_name", y="wins", color="ingredient_id",
                                   title="Top 20 Lojas com mais vitorias (preco mais baixo)",
                                   labels={"store_name": "Loja", "wins": "Dias como mais barata", "ingredient_id": "Ingrediente"},
                                   color_discrete_sequence=[CD_ORANGE, CD_PINK, CD_BLUE, "#FBBF5E", "#60A5FA"])
                    fig_w.update_layout(showlegend=True)
                    st.plotly_chart(fig_w, width='stretch')
                    st.dataframe(_pt_cols(df_w.head(50)), width='stretch', hide_index=True)
                    _export_csv_button(df_w, "vencedores.csv", key="csv_vencedores")

    with tab_tendencias:
        st.markdown("### Evolucao de precos por ingrediente")
        st.caption("Media, minimo e maximo de price_per_kg ao longo do tempo.")
        ing_t = st.selectbox("Ingrediente", ing_options, key="tendencia_ing")
        days_t = st.slider("Dias", 30, 365, 90, key="tendencia_dias")
        if st.button("Gerar Grafico", type="primary", key="btn_tendencias"):
            with st.spinner("Buscando precos..."):
                trends = get_price_trends(ing_t, days=days_t)
                if not trends:
                    info_box("Sem dados historicos para este ingrediente", "info")
                else:
                    df_t = pd.DataFrame(trends)
                    df_t["date"] = pd.to_datetime(df_t["date"])
                    fig_t = px.line(df_t, x="date", y=["avg_ppk", "min_ppk", "max_ppk"],
                                    title=f"{ing_t} - Evolucao de precos ({days_t} dias)",
                                    labels={"date": "Data", "value": "R$/kg", "variable": "Metrica"},
                                    color_discrete_map={"avg_ppk": CD_ORANGE, "min_ppk": "#10B981", "max_ppk": "#EF4444"})
                    fig_t.update_layout(legend={"orientation": "h", "y": -0.3})
                    st.plotly_chart(fig_t, width='stretch')
                    st.dataframe(_pt_cols(df_t.tail(30)), width='stretch', hide_index=True)
                    _export_csv_button(df_t, f"tendencias_{ing_t}.csv", key="csv_tendencias")

    with tab_cross:
        st.markdown("### Lojas com melhor ranking entre ingredientes")
        st.caption("Quantos ingredientes cada loja lidera (top 3) nos ultimos 90 dias.")
        if st.button("Calcular Ranking", type="primary", key="btn_cross"):
            with st.spinner("Buscando precos..."):
                ranking = get_cross_ingredient_ranking(days=90)
                if not ranking:
                    info_box("Sem dados suficientes", "info")
                else:
                    df_r = pd.DataFrame(ranking)
                    st.success(f"{len(df_r)} lojas ranqueadas")
                    fig_r = px.bar(df_r.head(15), x="store_name", y=["top1_count", "top3_count"],
                                   title="Top 15 Lojas - Ingredientes onde sao top 1 e top 3",
                                   labels={"store_name": "Loja", "value": "Ingredientes", "variable": "Posicao"},
                                   barmode="group",
                                   color_discrete_map={"top1_count": CD_ORANGE, "top3_count": CD_PINK})
                    fig_r.update_layout(legend={"orientation": "h", "y": -0.3})
                    st.plotly_chart(fig_r, width='stretch')
                    df_r_display = df_r.copy()
                    df_r_display.columns = ["Loja", "Top 1", "Top 3", "Total Ingredientes"]
                    st.dataframe(df_r_display.head(100), width='stretch', hide_index=True)
                    _export_csv_button(df_r, "cross_ranking.csv", key="csv_cross")


# ═══════════════════════════════════════════════════════════════

def tab_calculadora():
    section_title("Calculadora de Receita", "Calcule o custo e valor de venda dos seus doces")
    ingredients = _cached_get_active_ingredients()
    ing_options = {}
    if ingredients and isinstance(ingredients, list):
        for i in ingredients:
            if isinstance(i, dict) and i.get("canonical_name"):
                ing_options[i["canonical_name"]] = i
            elif isinstance(i, dict) and i.get("canonical"):
                ing_options[i["canonical"]] = i
    if not ing_options:
        info_box("Nenhum ingrediente cadastrado.", "warning")
        return
    ing_list = sorted(ing_options.keys())

    mode = st.radio("Modo", ["Simples", "Completo"], horizontal=True, key="calc_mode")
    is_complete = mode == "Completo"

    st.markdown("### Receita")
    col_nome, col_r, col_o, col_p = st.columns([3, 1, 1, 1])
    with col_nome:
        recipe_name = st.text_input("Nome da receita", placeholder="Ex: Brigadeiro Belga", key="calc_name")
    with col_r:
        yield_qty = st.number_input("Rendimento (un)", min_value=1, value=40, key="calc_yield")
    with col_o:
        overhead_pct = st.number_input("Custos adicionais %", min_value=0.0, max_value=100.0, value=15.0, step=1.0, key="calc_overhead")
    with col_p:
        profit_pct = st.number_input("Lucro %", min_value=0.0, max_value=1000.0, value=300.0, step=10.0, key="calc_profit")

    st.markdown("### Ingredientes")
    if "calc_rows" not in st.session_state:
        st.session_state.calc_rows = [{"id": 0}]
    row_id_counter = len(st.session_state.calc_rows)

    calc_prices = {}
    for row in st.session_state.calc_rows:
        rid = row["id"]
        cols = st.columns([3, 1, 1.5, 2, 0.5])
        with cols[0]:
            sel_ing = st.selectbox("Ingrediente", ing_list, key=f"calc_ing_{rid}", label_visibility="collapsed", placeholder="Selecione...")
        with cols[1]:
            qty = st.number_input("Qtd (g)", min_value=0.0, value=0.0, step=10.0, key=f"calc_qty_{rid}", label_visibility="collapsed")
        with cols[2]:
            if sel_ing and qty > 0:
                prices = get_cheapest_prices(sel_ing, top_n=3)
                calc_prices[rid] = prices
                if prices:
                    best = prices[0]
                    ppk = best.get("normalized", {}).get("price_per_kg", 0) if isinstance(best.get("normalized"), dict) else 0
                    if not ppk and "price_per_kg" in best:
                        ppk = best["price_per_kg"]
                    if not ppk:
                        ppk = prices[0].get("price_per_kg", 0)
                    cost = (qty / 1000) * ppk
                    st.markdown(
                        f'<div style="font-size:0.85rem;font-weight:700;color:var(--cd-orange);margin-top:1.4rem;">'
                        f"R$ {cost:.2f}</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("Sem precos")
            else:
                st.caption("—")
        with cols[3]:
            if prices and is_complete:
                store_opts = []
                for _pi, p in enumerate(prices):
                    ppk = p.get("normalized", {}).get("price_per_kg", 0) if isinstance(p.get("normalized"), dict) else 0
                    if not ppk:
                        ppk = p.get("price_per_kg", 0)
                    label = f"{p.get('store_name', '?')} — R$ {ppk:.2f}/kg"
                    store_opts.append(label)
                st.selectbox("Loja", store_opts, key=f"calc_store_{rid}", label_visibility="collapsed")
            elif prices:
                ppk = prices[0].get("normalized", {}).get("price_per_kg", 0) if isinstance(prices[0].get("normalized"), dict) else 0
                if not ppk:
                    ppk = prices[0].get("price_per_kg", 0)
                st.markdown(
                    f'<div class="store-opt" style="margin-top:1.4rem;font-size:0.8rem;">'
                    f"{prices[0].get('store_name', '?')}: R$ {ppk:.2f}/kg</div>",
                    unsafe_allow_html=True,
                )
        with cols[4]:
            if len(st.session_state.calc_rows) > 1 and st.button("✕", key=f"calc_del_{rid}", help="Remover ingrediente"):
                    st.session_state.calc_rows = [r for r in st.session_state.calc_rows if r["id"] != rid]
                    st.rerun()

    if st.button("+ Adicionar Ingrediente", width='stretch'):
        st.session_state.calc_rows.append({"id": row_id_counter})
        st.rerun()

    st.markdown("---")

    if st.button("Calcular", type="primary", width='stretch', key="calc_btn"):
        if not recipe_name or not recipe_name.strip():
            st.error("Informe o nome da receita.")
            st.stop()
        total_material = 0.0
        ingredients_used = []
        alerts = []
        for row in st.session_state.calc_rows:
            rid = row["id"]
            sel_ing = st.session_state.get(f"calc_ing_{rid}", "")
            qty = st.session_state.get(f"calc_qty_{rid}", 0.0)
            if not sel_ing or qty <= 0:
                continue
            prices = calc_prices.get(rid, [])
            if prices:
                ppk = prices[0].get("normalized", {}).get("price_per_kg", 0) if isinstance(prices[0].get("normalized"), dict) else 0
                if not ppk:
                    ppk = prices[0].get("price_per_kg", 0)
                cost_item = (qty / 1000) * ppk
                total_material += cost_item
                ingredients_used.append({"name": sel_ing, "qty_g": qty, "ppk": ppk, "cost": cost_item, "store": prices[0].get("store_name", "?")})
                if is_complete and len(prices) >= 3:
                    cheapest = prices[0]["normalized"]["price_per_kg"] if isinstance(prices[0].get("normalized"), dict) else prices[0].get("price_per_kg", 0)
                    most_expensive = prices[-1]["normalized"]["price_per_kg"] if isinstance(prices[-1].get("normalized"), dict) else prices[-1].get("price_per_kg", 0)
                    if most_expensive and cheapest and most_expensive > cheapest * 1.2:
                        alerts.append(f"{sel_ing}: diferenca de {((most_expensive/cheapest)-1)*100:.0f}% entre lojas")

        if total_material <= 0:
            st.error("Adicione pelo menos um ingrediente com quantidade valida.")
            st.stop()

        overhead_cost = total_material * (overhead_pct / 100)
        total_cost = total_material + overhead_cost
        unit_cost = total_cost / yield_qty
        sale_price = unit_cost * (1 + profit_pct / 100)
        total_profit = (sale_price * yield_qty) - total_cost

        st.markdown("## Resultado")
        if alerts:
            for a in alerts:
                st.markdown(f'<div class="cd-calc-alert">⚠️ {a}</div>', unsafe_allow_html=True)

        col_r1, col_r2, col_r3 = st.columns(3)
        with col_r1:
            st.markdown(
                f'<div class="cd-calc-result-card">'
                f'<div class="cd-calc-label">Custo Materiais</div>'
                f'<div class="cd-calc-value">R$ {total_material:.2f}</div>'
                f'</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="cd-calc-result-card">'
                f'<div class="cd-calc-label">Custos Adicionais ({overhead_pct:.0f}%)</div>'
                f'<div class="cd-calc-value">R$ {overhead_cost:.2f}</div>'
                f'</div>', unsafe_allow_html=True)
        with col_r2:
            st.markdown(
                f'<div class="cd-calc-result-card">'
                f'<div class="cd-calc-label">Custo Total</div>'
                f'<div class="cd-calc-value">R$ {total_cost:.2f}</div>'
                f'</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="cd-calc-result-card">'
                f'<div class="cd-calc-label">Custo por Unidade</div>'
                f'<div class="cd-calc-value">R$ {unit_cost:.2f}</div>'
                f'</div>', unsafe_allow_html=True)
        with col_r3:
            st.markdown(
                f'<div class="cd-calc-result-card">'
                f'<div class="cd-calc-label">Valor de Venda (unid.)</div>'
                f'<div class="cd-calc-value highlight">R$ {sale_price:.2f}</div>'
                f'</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="cd-calc-result-card">'
                f'<div class="cd-calc-label">Lucro Total</div>'
                f'<div class="cd-calc-value">R$ {total_profit:.2f}</div>'
                f'</div>', unsafe_allow_html=True)

        if is_complete:
            st.markdown("### Cenarios de Margem")
            scenarios = [
                ("Conservador", 100),
                ("Moderado", 200),
                ("Agressivo", 300),
            ]
            sc_cols = st.columns(3)
            for sci, (sname, spct) in enumerate(scenarios):
                sp = unit_cost * (1 + spct / 100)
                sprofit = (sp * yield_qty) - total_cost
                with sc_cols[sci]:
                    st.markdown(
                        f'<div class="cd-calc-scenario">'
                        f'<h4>{sname}</h4>'
                        f'<div class="price">R$ {sp:.2f}</div>'
                        f'<div class="profit">Lucro: R$ {sprofit:.2f}</div>'
                        f'<div style="font-size:0.7rem;color:var(--cd-text-secondary);">Margem: {spct}%</div>'
                        f'</div>', unsafe_allow_html=True)

        summary = (
            f"🧮 *{recipe_name}*\n"
            f"Rendimento: {yield_qty} un | Custos: {overhead_pct:.0f}% | Lucro: {profit_pct:.0f}%\n\n"
            f"Materiais: R$ {total_material:.2f}\n"
            f"Custo total: R$ {total_cost:.2f}\n"
            f"Custo/un: R$ {unit_cost:.2f}\n"
            f"**Venda/un: R$ {sale_price:.2f}**\n"
            f"Lucro total: R$ {total_profit:.2f}\n\n"
            f"Ingredientes:\n"
        )
        for ing in ingredients_used:
            summary += f"- {ing['name']}: {ing['qty_g']:.0f}g x R$ {ing['ppk']:.2f}/kg = R$ {ing['cost']:.2f} ({ing['store']})\n"
        summary += "\nCustoDoce -- cotacao automatica"

        col_share, col_save, col_tg = st.columns(3)
        with col_share:
            if st.button("Copiar Resumo", width='stretch', key="calc_copy"):
                st.code(summary, language="")
                st.toast("Resumo copiado! Cole onde quiser.", icon="✅")
        with col_save:
            if st.button("Salvar Receita", type="primary", width='stretch', key="calc_save"):
                try:
                    client = get_service_client()
                    recipe_data = {
                        "name": recipe_name.strip(),
                        "yield_qty": yield_qty,
                        "overhead_pct": overhead_pct,
                        "profit_pct": profit_pct,
                    }
                    recipe_res = client.table("recipes").insert(recipe_data).execute()
                    if recipe_res.data:
                        recipe_id = recipe_res.data[0]["id"]
                        for ing in ingredients_used:
                            item_data = {
                                "recipe_id": recipe_id,
                                "ingredient_id": ing["name"],
                                "quantity_g": ing["qty_g"],
                                "selected_store": ing["store"],
                                "price_per_kg": ing["ppk"],
                            }
                            client.table("recipe_items").insert(item_data).execute()
                        st.success(f"Receita '{recipe_name}' salva com {len(ingredients_used)} ingredientes!")
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")
        with col_tg:
            tg_token = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
            tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
            if tg_token and tg_chat:
                if st.button("Enviar via Telegram", width='stretch', key="calc_tg"):
                    try:
                        resp = httpx.post(
                            f"https://api.telegram.org/bot{tg_token}/sendMessage",
                            json={"chat_id": tg_chat, "text": summary, "parse_mode": "Markdown"},
                            timeout=15,
                        )
                        if resp.status_code == 200:
                            st.toast("Enviado via Telegram!", icon="📬")
                        else:
                            st.error(f"Erro Telegram: {resp.status_code}")
                    except Exception as e:
                        st.error(f"Falha no Telegram: {e}")
            else:
                st.button("Telegram (sem config)", disabled=True, help="Configure TELEGRAM_TOKEN e TELEGRAM_CHAT_ID", width='stretch', key="calc_tg_disabled")

    st.markdown("---")
    if is_complete:
        st.markdown("### Receitas Salvas")
        try:
            client = get_service_client()
            saved = client.table("recipes").select("*").order("created_at", desc=True).limit(10).execute()
            if saved.data:
                for r in saved.data:
                    with st.expander(f"{r.get('name', 'Sem nome')} — {r.get('yield_qty', '?')} un"):
                        st.caption(f"Criada em {r.get('created_at', '')[:10]} | Overhead: {r.get('overhead_pct', 0)}% | Lucro: {r.get('profit_pct', 0)}%")
                        items = client.table("recipe_items").select("*").eq("recipe_id", r["id"]).execute()
                        if items.data:
                            for it in items.data:
                                st.markdown(f"- {it.get('ingredient_id', '?')}: {it.get('quantity_g', 0):.0f}g — R$ {it.get('price_per_kg', 0):.2f}/kg ({it.get('selected_store', '?')})")
                        if st.button("Carregar", key=f"calc_load_{r['id']}"):
                            st.session_state.calc_name = r.get("name", "")
                            st.session_state.calc_yield = r.get("yield_qty", 40)
                            st.session_state.calc_overhead = float(r.get("overhead_pct", 15))
                            st.session_state.calc_profit = float(r.get("profit_pct", 300))
                            if items.data:
                                st.session_state.calc_rows = []
                                for idx, it in enumerate(items.data):
                                    st.session_state.calc_rows.append({"id": idx})
                                    st.session_state[f"calc_ing_{idx}"] = it.get("ingredient_id", "")
                                    st.session_state[f"calc_qty_{idx}"] = float(it.get("quantity_g", 0))
                            st.rerun()
            else:
                st.caption("Nenhuma receita salva ainda.")
        except Exception:
            st.caption("Nao foi possivel carregar receitas salvas.")


# ═══════════════════════════════════════════════════════════════

PAGE_HANDLERS = {
    "visao_geral": tab_visao_geral,
    "precos": tab_precos,
    "historico": tab_historico,
    "flyers": tab_flyers,
    "revisao": tab_revisao,
    "fontes": tab_fontes,
    "ranking": tab_ranking,
    "insights": tab_insights,
    "lojas": tab_lojas,
    "ingredientes": tab_ingredientes,
    "alertas": tab_alertas,
    "scrapers": tab_scrapers,
    "relatorios": tab_relatorios,
    "config": tab_config,
    "calculadora": tab_calculadora,
    "diagnostico": tab_diagnostico,
}


# Cache version — increment to force full invalidation on next deploy
CACHE_VERSION = 2


def _check_clear_cache():
    """Handle cache clear triggers: version mismatch or query param."""
    qp = st.query_params
    if qp.get("clear_cache") == "1":
        st.cache_data.clear()
        st.session_state.cache_version = CACHE_VERSION
        qp.clear()
        st.rerun()
    if st.session_state.get("cache_version", 0) != CACHE_VERSION:
        st.cache_data.clear()
        st.session_state.cache_version = CACHE_VERSION


def main():
    _check_clear_cache()

    if not require_auth():
        return

    plotly_theme()
    inject_css()
    render_sidebar()

    if get_config("features.offline.enabled", False):
        msg = get_config("features.offline.banner_message", "Modo Offline")
        st.warning(msg, icon="⚠️")
        st.session_state.offline_mode = True
    else:
        st.session_state.offline_mode = False

    page = st.session_state.get("page", "visao_geral")
    handler = PAGE_HANDLERS.get(page)
    if handler:
        handler()
    else:
        st.error(f"Pagina desconhecida: {page}")


if __name__ == "__main__":
    main()

