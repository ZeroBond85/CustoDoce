import os

os.environ.setdefault("ADMIN_PASSWORD", "custodoce2907")

from datetime import datetime

from services.config import get as get_config, reload as reload_config

from dotenv import load_dotenv
import yaml
import pandas as pd
import streamlit as st
import plotly.express as px

from services.price_service import (
    get_latest_prices,
    search_prices,
    get_price_history,
    get_review_queue,
    approve_review_item,
    reject_review_item,
)
from dashboard.components.ui import (
    inject_css,
    section_title,
    info_box,
    plotly_theme,
)
from dashboard.components.layout import render_sidebar
from dashboard.login_page import render_login, render_setup_first_user

load_dotenv()

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


@st.cache_data(ttl=600)
def load_ingredients():
    with open(INGREDIENTS_FILE) as f:
        data = yaml.safe_load(f)
    return data.get("ingredients", [])


def require_auth():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        inject_css()
        tab1, tab2 = st.tabs(["Entrar", "Primeiro Acesso"])
        with tab1:
            render_login()
        with tab2:
            render_setup_first_user()
        return False
    return True


def _get_kg(df):
    vals = df["normalized"].apply(
        lambda x: x.get("price_per_kg", 0) if isinstance(x, dict) else 0
    )
    return vals


def _render_kpi_prices(df):
    total = len(df)
    lojas = df["store_name"].nunique() if "store_name" in df.columns else 0
    matched = len(df[df.get("confidence", 1) >= 0.8])
    review = len(get_review_queue())
    st.markdown(
        '<div class="cd-kpi-row" style="display:flex;gap:0.75rem;margin-bottom:1.5rem;">'
        f'<div style="flex:1;"><div class="cd-metric"><div class="label">Total Precos</div><div class="value">{total}</div></div></div>'
        f'<div style="flex:1;"><div class="cd-metric"><div class="label">Lojas</div><div class="value">{lojas}</div></div></div>'
        f'<div style="flex:1;"><div class="cd-metric"><div class="label">Confiaveis >=80%</div><div class="value">{matched}</div></div></div>'
        f'<div style="flex:1;"><div class="cd-metric"><div class="label">Fila Revisao</div><div class="value">{review}</div></div></div>'
        "</div>",
        unsafe_allow_html=True,
    )


def _render_kpi_flyers(df):
    try:
        from services.flyer_service import get_recent_flyers
        flyers = get_recent_flyers(days=3)
        f_total = len(flyers) if flyers else 0
        f_processed = len([f for f in (flyers or []) if f.get("ocr_status") in ("done", "processed")])
        hoje = datetime.utcnow().date()
        precos_hoje = 0
        desatualizados = 0
        if "collected_at" in df.columns:
            for val in df["collected_at"]:
                if pd.notna(val):
                    dt = pd.to_datetime(val)
                    if dt.date() == hoje:
                        precos_hoje += 1
                    if (datetime.utcnow() - dt).days > 7:
                        desatualizados += 1
        st.markdown(
            '<div class="cd-kpi-row" style="display:flex;gap:0.75rem;margin-bottom:1.5rem;">'
            f'<div style="flex:1;"><div class="cd-metric" style="border-left-color:#3B7DD8;"><div class="label">Flyers (3d)</div><div class="value">{f_total}</div></div></div>'
            f'<div style="flex:1;"><div class="cd-metric" style="border-left-color:#10B981;"><div class="label">Processados</div><div class="value">{f_processed}</div></div></div>'
            f'<div style="flex:1;"><div class="cd-metric" style="border-left-color:#F59E0B;"><div class="label">Precos Hoje</div><div class="value">{precos_hoje}</div></div></div>'
            f'<div style="flex:1;"><div class="cd-metric" style="border-left-color:#EF4444;"><div class="label">Desatualizados (+7d)</div><div class="value">{desatualizados}</div></div></div>'
            "</div>",
            unsafe_allow_html=True,
        )
    except Exception:
        pass  # nosec B110


def _render_latest_prices(df):
    st.markdown("### Ultimos Precos")
    cols = ["store_name", "ingredient_id", "raw_product", "raw_price", "raw_unit", "tier", "confidence", "collected_at"]
    cols = [c for c in cols if c in df.columns]
    st.dataframe(df[cols].sort_values("collected_at", ascending=False).head(100), use_container_width=True, hide_index=True)


def _render_boxplot(df):
    if "normalized" not in df.columns or not df["normalized"].notna().any():
        return
    df_norm = df[df["normalized"].notna() & (df["price_per_kg"] > 0)].copy()
    if df_norm.empty:
        return
    fig = px.box(df_norm, x="ingredient_id", y="price_per_kg", title="Preco por kg por Ingrediente",
                 labels={"ingredient_id": "Ingrediente", "price_per_kg": "R$/kg"},
                 color_discrete_sequence=[CD_ORANGE])
    st.plotly_chart(fig, use_container_width=True)


def _render_coverage_heatmap(df):
    st.markdown("### Cobertura de Coleta")
    try:
        ingredients = load_ingredients()
        ing_names = [i["canonical"] for i in ingredients[:11]]
        stores = sorted(df["store_name"].unique().tolist())
        if not stores or not ing_names:
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
                if ts:
                    try:
                        days_ago = (datetime.utcnow() - pd.to_datetime(ts)).days
                        row[s] = "hoje" if days_ago <= 3 else "semana" if days_ago <= 7 else "antigo"
                    except Exception:
                        row[s] = "erro"
            matrix.append(row)
        df_heat = pd.DataFrame(matrix)

        def color_cell(val):
            if val == "hoje":
                return "background:#D1FAE5;color:#065F46;font-weight:700;"
            if val == "semana":
                return "background:#FEF3C7;color:#92400E;font-weight:700;"
            if val == "antigo":
                return "background:#FEE2E2;color:#991B1B;font-weight:700;"
            return "background:#F3F4F6;color:#9CA3AF;"

        st.dataframe(df_heat.style.map(color_cell), use_container_width=True, hide_index=True)
    except Exception as e:
        st.caption(f"Grade indisponivel: {e}")


def _render_variation_alerts(df):
    st.markdown("### Alertas de Variacao")
    alert_pct = get_config("features.alerts.price_variation_pct", 15)
    try:
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
                icon = "subiu" if change > 0 else "caiu"
                color = "#EF4444" if change > 0 else "#10B981"
                st.markdown(
                    f'<div style="padding:0.5rem 0.75rem;border-radius:8px;background:#FFF;border:1px solid #F0E6DB;margin-bottom:0.5rem;display:flex;justify-content:space-between;">'
                    f"<span><strong>{ing_name}</strong> {icon} <strong>{abs(change):.0f}%</strong></span>"
                    f'<span style="color:{color};font-weight:700;">R$ {current:.2f}/kg (media: R$ {avg:.2f}/kg)</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
    except Exception as e:
        st.caption(f"Alertas indisponiveis: {e}")


def tab_visao_geral():
    section_title("Visao Geral", "Resumo do estado atual dos precos")
    prices = get_latest_prices()
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
    ingredients = load_ingredients()
    ingredient_options = {i["canonical"]: i for i in ingredients}
    selected = st.selectbox(
        "Selecione o ingrediente",
        options=list(ingredient_options.keys()),
        index=0 if ingredient_options else 0,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        sort_by = st.selectbox(
            "Ordenar por", ["price_per_kg", "price_per_un", "raw_price"]
        )
    with col2:
        sort_order = st.selectbox("Ordem", ["asc", "desc"])
    with col3:
        limit = st.number_input("Limite", min_value=5, max_value=100, value=30)

    if st.button("Buscar", type="primary"):
        prices = search_prices(
            selected, sort_by=sort_by, sort_order=sort_order, limit=limit
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
                    store = row.get("store_name", "?")
                    product = row.get("raw_product", "?")
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
                        f'<div style="font-size:0.75rem;color:#9CA3AF;">{product[:40]}</div>'
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
                    st.plotly_chart(fig, use_container_width=True)

            display_cols = [
                "store_name",
                "raw_product",
                "raw_price",
                "raw_unit",
                "tier",
                "confidence",
                "collected_at",
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

            df_display = df[display_cols].head(limit).copy()
            min_price_idx = None
            if "price_per_kg" in df.columns and sort_by in df.columns:
                valid = df_display[
                    df_display.get("price_per_kg", pd.Series([0])) > 0
                ].index
                if not valid.empty:
                    if sort_order == "asc":
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
                st.dataframe(styled, use_container_width=True, hide_index=True)
            else:
                st.dataframe(df_display, use_container_width=True, hide_index=True)

            if get_config("features.export.csv_enabled", True):
                csv = df_display.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Exportar CSV",
                    csv,
                    f"precos_{selected}_{datetime.utcnow().strftime('%Y%m%d')}.csv",
                    "text/csv",
                    key=f"csv_precos_{selected}",
                    use_container_width=True,
                )
        else:
            info_box(f"Nenhum preco encontrado para '{selected}'", "warning")


def _format_kg(p):
    if isinstance(p, dict):
        return p.get("price_per_kg", 0)
    return 0

def tab_historico():
    section_title("Historico de Precos", "Tendencias e variacoes ao longo do tempo")
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
        history = get_price_history(selected, days=days)
        if not history:
            info_box(f"Nenhum historico disponivel para '{selected}' no periodo.", "info")
            return

        df = pd.DataFrame(history)
        df["collected_at"] = pd.to_datetime(df["collected_at"])
        df = df.sort_values("collected_at")

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
        st.plotly_chart(fig, use_container_width=True)

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
        st.dataframe(store_stats, use_container_width=True, hide_index=True)

        st.markdown("### Dados Brutos")
        display_cols = [c for c in ["store_name", "raw_product", "raw_price", "raw_unit", "collected_at"] if c in df.columns]
        if "price_per_kg" in df.columns:
            df["R$/kg"] = df["price_per_kg"].apply(lambda x: f"R$ {x:.2f}" if x > 0 else "—")
            display_cols.append("R$/kg")
        st.dataframe(df[display_cols].tail(100), use_container_width=True, hide_index=True)

        if get_config("features.export.csv_enabled", True):
            csv_data = store_stats.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Exportar Cobertura CSV",
                csv_data,
                f"cobertura_{selected}_{datetime.utcnow().strftime('%Y%m%d')}.csv",
                "text/csv",
                key="csv_cobertura",
                use_container_width=True,
            )
            csv_full = df[display_cols].to_csv(index=False).encode("utf-8")
            st.download_button(
                "Exportar Dados Brutos CSV",
                csv_full,
                f"historico_{selected}_{datetime.utcnow().strftime('%Y%m%d')}.csv",
                "text/csv",
                key="csv_historico",
                use_container_width=True,
            )


def _flyer_status_color(status):
    m = {"done": "#10B981", "processed": "#10B981", "pending": "#F59E0B", "failed": "#EF4444", "error": "#EF4444"}
    return m.get(status.lower(), "#6B7280")

def _flyer_status_label(status):
    m = {"done": "processado", "processed": "processado", "pending": "pendente", "failed": "falha", "error": "falha"}
    return m.get(status.lower(), status)

def tab_flyers():
    section_title("Flyers & OCR", "Folhetos coletados e status de processamento")
    try:
        from services.flyer_service import get_recent_flyers

        flyers = get_recent_flyers(limit=100)
        if not flyers:
            info_box("Nenhum flyer coletado ainda.", "info")
            return

        df = pd.DataFrame(flyers)
        df["collected_at"] = pd.to_datetime(df["collected_at"])

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

        cards_html = '<div class="cd-flyer-grid">'
        for _, f in filtered.head(50).iterrows():
            status = f.get("ocr_status", "pending")
            color = _flyer_status_color(status)
            label = _flyer_status_label(status)
            store = f.get("store_name", "?")
            title = f.get("flyer_title", f.get("title", ""))[:60]
            products = int(f.get("products_extracted", 0))
            collected = f["collected_at"].strftime("%d/%m/%Y") if pd.notna(f["collected_at"]) else "?"
            cards_html += (
                f'<div class="cd-flyer-card" id="flyer_{f["id"]}">'
                f'<div class="store">{store}</div>'
                f'<div class="title">{title}</div>'
                f'<div class="meta">'
                f'<span class="meta-item" style="color:{color};font-weight:700;">{label}</span>'
                f'<span class="products">{products} produtos</span>'
                f'<span class="date">{collected}</span>'
                f'</div></div>'
            )
        cards_html += "</div>"
        st.markdown(cards_html, unsafe_allow_html=True)
        st.caption(f"Exibindo {min(len(filtered), 50)} de {len(filtered)} flyers")

        st.markdown("### Detalhe do Flyer")
        flyer_options = {}
        for _, f in filtered.iterrows():
            label = f"{f.get('store_name', '?')} — {f.get('flyer_title', f.get('title', ''))[:50]}"
            flyer_options[label] = f
        if flyer_options:
            selected_label = st.selectbox("Selecione um flyer para ver detalhes", list(flyer_options.keys()))
            selected = flyer_options[selected_label]
            st.markdown(
                f'<div class="cd-flyer-detail">'
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;margin-bottom:1rem;">'
                f'<div><strong>Loja:</strong> {selected.get("store_name", "?")}</div>'
                f'<div><strong>Regiao:</strong> {selected.get("region", "?")}</div>'
                f'<div><strong>Cidade:</strong> {selected.get("city", "?")}</div>'
                f'<div><strong>Status OCR:</strong> <span style="color:{_flyer_status_color(selected.get("ocr_status", "pending"))};font-weight:700;">{_flyer_status_label(selected.get("ocr_status", "pending"))}</span></div>'
                f'<div><strong>Produtos:</strong> {int(selected.get("products_extracted", 0))}</div>'
                f'<div><strong>Coleta:</strong> {pd.to_datetime(selected["collected_at"]).strftime("%d/%m/%Y %H:%M") if "collected_at" in selected else "?"}</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            img_url = selected.get("image_url", "")
            if img_url:
                st.image(img_url, use_container_width=True)
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
    review_items = get_review_queue()

    if review_items:
        st.markdown(f"**{len(review_items)} itens** aguardando revisao")

        for item in review_items[:50]:
            item_id = item.get("id")
            raw_product = item.get("raw_product", "?")
            confidence = item.get("confidence", 0)
            store_name = item.get("store_name", "?")
            raw_price = item.get("raw_price", 0)
            raw_unit = item.get("raw_unit", "")
            suggestions = item.get("suggestions", [])

            with st.container(border=True):
                cols = st.columns([3, 2, 1, 1])
                with cols[0]:
                    st.markdown(f"**{raw_product}**")
                    st.caption(
                        f"Loja: {store_name} | Confianca: {confidence * 100:.0f}%"
                    )
                with cols[1]:
                    st.markdown(f"R$ {float(raw_price):.2f} {raw_unit}")
                with cols[2]:
                    if st.button(
                        "Aprovar", key=f"app_{item_id}", use_container_width=True
                    ):
                        chosen = st.session_state.get(f"ingredient_{item_id}", "")
                        if chosen == "Outro...":
                            chosen = st.session_state.get(
                                f"custom_ingredient_{item_id}", ""
                            )
                        if chosen:
                            approve_review_item(item_id, chosen)
                            st.rerun()
                with cols[3]:
                    if st.button(
                        "Rejeitar", key=f"rej_{item_id}", use_container_width=True
                    ):
                        reject_review_item(item_id)
                        st.rerun()

                options = suggestions + ["Outro..."]
                selected = st.selectbox(
                    "Ingrediente",
                    options,
                    key=f"ingredient_{item_id}",
                    index=0 if suggestions else len(options) - 1,
                    label_visibility="collapsed",
                )
                if selected == "Outro..." or not suggestions:
                    st.text_input(
                        "Digite o nome do ingrediente",
                        key=f"custom_ingredient_{item_id}",
                        placeholder="Ex: Leite Condensado Integral",
                        label_visibility="collapsed",
                    )
    else:
        info_box("Nenhum item na fila de revisao!", "success")


def tab_lojas():
    section_title("Lojas", "Gerenciamento de lojas e categorias")
    try:
        with open("config/stores.yaml") as f:
            stores_data = yaml.safe_load(f) or {}
        stores = stores_data.get("stores", [])
    except FileNotFoundError:
        info_box("Arquivo config/stores.yaml nao encontrado", "error")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Lojas", len(stores))
    tiers = [s.get("tier", 3) for s in stores]
    col2.metric("Tiers", f"{min(tiers)}-{max(tiers)}" if tiers else "—")
    col3.metric("Ativas", len([s for s in stores if s.get("is_active", True)]))
    col4.metric("Cidades", len(set(s.get("city", "") for s in stores if s.get("city"))))

    col_s1, col_s2 = st.columns([3, 1])
    with col_s2:
        tier_filter = st.selectbox("Filtrar Tier", ["todas", 1, 2, 3, 4])
    with col_s1:
        search = st.text_input("Buscar loja", placeholder="Nome ou cidade...")

    filtered = stores
    if tier_filter != "todas":
        filtered = [s for s in filtered if s.get("tier") == tier_filter]
    if search:
        q = search.lower()
        filtered = [s for s in filtered if q in s.get("name", "").lower() or q in s.get("city", "").lower()]

    if filtered:
        df_stores = pd.DataFrame(filtered)
        cols = ["name", "tier", "type", "logistics", "city", "zone", "is_active"]
        cols = [c for c in cols if c in df_stores.columns]
        st.dataframe(df_stores[cols], use_container_width=True, hide_index=True)
    else:
        info_box("Nenhuma loja encontrada com esse filtro.", "info")

    with st.expander("Editar YAML (stores.yaml)"):
        edited = st.text_area("Conteudo YAML", yaml.dump({"stores": stores}), height=300, font="monospace")
        if st.button("Validar YAML", type="primary"):
            try:
                parsed = yaml.safe_load(edited)
                assert isinstance(parsed, dict) and "stores" in parsed
                assert isinstance(parsed["stores"], list)
                st.success(f"YAML valido! {len(parsed['stores'])} lojas encontradas.")
            except Exception as e:
                st.error(f"YAML invalido: {e}")

    with st.expander("Schema da Loja"):
        st.code("""
name: str (obrigatorio)
tier: int 1-4 (obrigatorio)
type: str (atacado, varejo, ecommerce, manual)
logistics: str (pickup_local, delivery, online)
city: str
zone: str
coverage: str
collection_method: str (pdf, api, website, manual, spreadsheet)
is_active: bool
config: dict (opcional)
""")


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
            from parsers.matcher import match_ingredient
            ingredients = load_ingredients()
            result = match_ingredient(product, ingredients)
            if result:
                st.success(f"**Match:** {result['matched']} (confianca: {result['confidence']:.1%})")
                if result.get("suggestions"):
                    with st.expander("Sugestoes"):
                        for s in result["suggestions"]:
                            st.write(f"- {s['name']} ({s['score']:.1%})")
            else:
                info_box("Nenhum match encontrado.", "warning")
        except Exception as e:
            st.error(f"Erro: {e}")


def tab_ingredientes():
    section_title("Ingredientes", "Ingredientes monitorados e seus aliases")
    ingredients = load_ingredients()

    tab_visual, tab_tester = st.tabs(["Visualizacao", "Testadores"])

    with tab_visual:
        categories = {}
        for ing in ingredients:
            cat = ing.get("category", "outros")
            categories.setdefault(cat, []).append(ing)

        for cat, items in categories.items():
            with st.expander(f"{cat.upper()} ({len(items)})"):
                for item in items:
                    aliases = item.get("aliases", [])
                    alias_str = ", ".join(aliases[:5]) if aliases else "—"
                    st.markdown(f"**{item['canonical']}**")
                    st.caption(f"Aliases: {alias_str}")
                    st.divider()

        st.markdown("---")
        st.code(yaml.dump({"ingredients": ingredients}), language="yaml")

    with tab_tester:
        _test_normalizer()
        st.markdown("---")
        _test_matcher()


def _render_schedule_info():
    st.markdown("### Agendamento (GitHub Actions)")
    path = ".github/workflows/scrape.yml"
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        import re
        crons = re.findall(r"cron:\s*'([^']+)'", content)
        st.markdown(
            '<div style="display:flex;gap:0.75rem;flex-wrap:wrap;">'
            + "".join(
                f'<div style="flex:1;min-width:200px;background:#FFF;padding:0.75rem 1rem;border-radius:10px;border:1px solid #F0E6DB;">'
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
            if st.button("Salvar Agendamento", type="primary", use_container_width=True):
                new_content = content
                for i, (old, new) in enumerate(zip(crons, new_crons)):
                    new_content = new_content.replace(
                        f"cron: '{old}'", f"cron: '{new}'"
                    )
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                st.success("Agendamento atualizado!")

    except FileNotFoundError:
        info_box("Arquivo scrape.yml nao encontrado.", "warning")


def tab_scrapers():
    section_title("Scrapers & Logs", "Execucao manual e acompanhamento de logs")
    _render_schedule_info()
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "Forcar Coleta Agora", type="primary", use_container_width=True
        ):
            gh_pat = os.environ.get("GH_PAT")
            repo = os.environ.get("GITHUB_REPOSITORY", "CustoDoce/CustoDoce")
            if gh_pat:
                import requests

                resp = requests.post(
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
    with col2:
        st.info("Clique para acionar a coleta manual via GitHub Actions.")

    try:
        from services.supabase_client import get_service_client

        client = get_service_client()
        logs = (
            client.table("scraping_logs")
            .select("*")
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        if logs.data:
            df_logs = pd.DataFrame(logs.data)
            st.dataframe(
                df_logs[
                    [
                        "store_name",
                        "status",
                        "items_found",
                        "duration_ms",
                        "created_at",
                    ]
                ]
                if "store_name" in df_logs.columns
                else df_logs,
                use_container_width=True,
                hide_index=True,
            )
    except Exception as e:
        info_box(f"Erro ao carregar logs: {e}", "warning")


def _build_report_html(ingredient: str, days: int, prices: list) -> str:
    hoje = datetime.utcnow().strftime("%d/%m/%Y")
    rows = ""
    for p in prices[:20]:
        store = p.get("store_name", "?")
        product = p.get("raw_product", "?")
        price = float(p.get("raw_price", 0))
        unit = p.get("raw_unit", "")
        ppk = ""
        if isinstance(p.get("normalized"), dict):
            ppk = p["normalized"].get("price_per_kg", 0)
            ppk = f"R$ {ppk:.2f}/kg" if ppk else ""
        rows += f"<tr><td>{store}</td><td>{product[:50]}</td><td>R$ {price:.2f} {unit}</td><td>{ppk}</td></tr>"
    return f"""<html><body style="font-family:Nunito,sans-serif;background:#FFF9F5;padding:20px;">
<h2 style="color:#F59E42;">CustoDoce - Relatorio de Precos</h2>
<p style="color:#8B7355;">{ingredient} - Ultimos {days} dias - {hoje}</p>
<table style="width:100%;border-collapse:collapse;background:#FFF;border-radius:10px;overflow:hidden;">
<tr style="background:#F59E42;color:#FFF;"><th>Loja</th><th>Produto</th><th>Preco</th><th>R$/kg</th></tr>
{rows}</table>
<p style="color:#9CA3AF;font-size:0.8rem;margin-top:20px;">Gerado automaticamente pelo CustoDoce em {hoje}</p>
</body></html>"""


def _test_smtp(gmail_user: str, gmail_pass: str, to_email: str):
    import smtplib
    from email.mime.text import MIMEText
    try:
        msg = MIMEText("Teste de conexao SMTP - CustoDoce\n\nSe voce recebeu este email, o SMTP esta funcionando!", _charset="utf-8")
        msg["Subject"] = "🔧 Teste SMTP CustoDoce"
        msg["From"] = f"CustoDoce <{gmail_user}>"
        msg["To"] = to_email
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.starttls()
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)
        return True, "Email de teste enviado com sucesso!"
    except Exception as e:
        return False, str(e)


def _test_telegram(token: str, chat_id: str):
    import httpx
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
    tab_builder, tab_smtp, tab_telegram = st.tabs(["Relatorio", "Testar SMTP", "Testar Telegram"])

    with tab_builder:
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
            pass

        if st.button("Gerar Preview", type="primary", use_container_width=True):
            prices = get_price_history(selected, days=days)
            if prices:
                html = _build_report_html(selected, days, prices[:limit])
                st.markdown("### Preview do Relatorio")
                st.components.v1.html(html, height=500, scrolling=True)
                st.markdown("### Enviar por Email")
                gmail_user = os.environ.get("GMAIL_USER", "")
                to_email = os.environ.get("ALERT_EMAIL_TO", "")
                if gmail_user and to_email:
                    if st.button("Enviar Relatorio Agora", key="send_report", use_container_width=True):
                        try:
                            from services.email_service import send_daily_report
                            send_daily_report(report_html=html, to_email=to_email,
                                              subject=f"📊 Relatorio {selected} - {days}d")
                            st.success("Relatorio enviado com sucesso!")
                        except Exception as e:
                            st.error(f"Erro ao enviar: {e}")
                else:
                    info_box("Configure GMAIL_USER e ALERT_EMAIL_TO nas secrets.", "warning")
            else:
                info_box(f"Nenhum dado para '{selected}' no periodo.", "info")

    with tab_smtp:
        if not get_config("features.email.enabled", True):
            info_box("Email desabilitado em config/features.yaml", "warning")
        else:
            st.markdown("### Testar Conexao SMTP (Gmail)")
            gmail_user = st.text_input("GMAIL_USER", value=os.environ.get("GMAIL_USER", ""), key="smtp_user")
            gmail_pass = st.text_input("GMAIL_APP_PASSWORD", type="password", value=os.environ.get("GMAIL_APP_PASSWORD", ""), key="smtp_pass")
            to_email = st.text_input("Email de teste", value=os.environ.get("ALERT_EMAIL_TO", ""), key="smtp_to")
            if st.button("Testar SMTP", type="primary", use_container_width=True):
                ok, msg = _test_smtp(gmail_user, gmail_pass, to_email)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

    with tab_telegram:
        if not get_config("features.telegram.enabled", True):
            info_box("Telegram desabilitado em config/features.yaml", "warning")
        else:
            st.markdown("### Testar Conexao Telegram")
            token = st.text_input("TELEGRAM_TOKEN", type="password", value=os.environ.get("TELEGRAM_TOKEN", ""), key="tg_token")
            chat_id = st.text_input("TELEGRAM_CHAT_ID", value=os.environ.get("TELEGRAM_CHAT_ID", ""), key="tg_chat")
            if st.button("Testar Telegram", type="primary", use_container_width=True):
                ok, msg = _test_telegram(token, chat_id)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)


SECRET_GROUPS = {
    "Supabase": ["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"],
    "Autenticacao": ["AUTH_SECRET_KEY", "ADMIN_PASSWORD_HASH", "TOTP_SECRET", "TOTP_ENABLED"],
    "Telegram": ["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"],
    "Email": ["GMAIL_USER", "GMAIL_APP_PASSWORD", "ALERT_EMAIL_TO"],
    "GitHub": ["GH_PAT"],
}


def _mask_val(v):
    if not v:
        return "Nao configurado"
    if len(v) > 8:
        return v[:4] + "*" * (len(v) - 8) + v[-4:]
    return v


def tab_config():
    section_title("Configuracao", "Configuracoes do sistema")
    tab_env, tab_ing, tab_stores, tab_features = st.tabs(
        ["Variaveis de Ambiente", "Ingredientes", "Lojas", "Features"]
    )

    with tab_env:
        st.markdown("### Configuracao de Email para Relatorios")
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            env_gmail = st.text_input(
                "GMAIL_USER (seu email)",
                value=os.environ.get("GMAIL_USER", ""),
                key="env_gmail_user",
                help="Seu endereco Gmail que enviara os relatorios",
            )
            os.environ["GMAIL_USER"] = env_gmail
        with col_m2:
            env_pass = st.text_input(
                "GMAIL_APP_PASSWORD (senha de app)",
                value=os.environ.get("GMAIL_APP_PASSWORD", ""),
                type="password",
                key="env_gmail_pass",
                help="Senha de 16 caracteres gerada em myaccount.google.com/security",
            )
            os.environ["GMAIL_APP_PASSWORD"] = env_pass
        with col_m3:
            env_to = st.text_input(
                "ALERT_EMAIL_TO (email destino)",
                value=os.environ.get("ALERT_EMAIL_TO", ""),
                key="env_gmail_to",
                help="Para qual email os relatorios serao enviados",
            )
            os.environ["ALERT_EMAIL_TO"] = env_to
        if env_gmail and env_pass and env_to:
            if st.button("Testar Envio de Email", key="test_email_cfg", use_container_width=True):
                ok, msg = _test_smtp(env_gmail, env_pass, env_to)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
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
            if st.button(toggle_label, use_container_width=True):
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
                        if new_val != current:
                            os.environ[k] = new_val
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
                    if st.button(
                        f"Salvar {group}",
                        key=f"save_{group}",
                        type="primary",
                        use_container_width=True,
                    ):
                        lines = []
                        env_path = ".env"
                        try:
                            with open(env_path, encoding="utf-8") as f:
                                lines = f.readlines()
                        except FileNotFoundError:
                            pass
                        # atualiza linhas existentes ou adiciona
                        existing_keys = {k: False for k in keys}
                        new_lines = []
                        for line in lines:
                            stripped = line.strip()
                            if stripped and "=" in stripped:
                                ek = stripped.split("=", 1)[0].strip()
                                if ek in existing_keys:
                                    new_val = os.environ.get(ek, "")
                                    new_lines.append(f'{ek}="{new_val}"\n')
                                    existing_keys[ek] = True
                                else:
                                    new_lines.append(line)
                            else:
                                new_lines.append(line)
                        for k, found in existing_keys.items():
                            if not found:
                                new_val = os.environ.get(k, "")
                                new_lines.append(f'{k}="{new_val}"\n')
                        with open(env_path, "w", encoding="utf-8") as f:
                            f.writelines(new_lines)
                        st.success(f"{group} salvo com sucesso!")

    with tab_ing:
        st.markdown("**Ingredientes (ingredients.yaml)**")
        ingredients = load_ingredients()
        st.code(yaml.dump({"ingredients": ingredients}), language="yaml")

    with tab_stores:
        st.markdown("**Lojas (stores.yaml)**")
        try:
            with open("config/stores.yaml") as f:
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
            if st.button("Recarregar Configuracoes", use_container_width=True):
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
    with open(path) as f:
        yaml.safe_load(f)
    return f"{path} valido"


def _test_auth():
    from services.auth import hash_password, verify_password
    h = hash_password("test")
    assert verify_password("test", h)
    return "PBKDF2-HMAC-SHA256 600k iter"


def _test_rate_limiter():
    from services.rate_limiter import RateLimiter
    rl = RateLimiter()
    assert rl.is_limited("test_key") is False
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
                "AUTH_SECRET_KEY", "TELEGRAM_TOKEN", "GMAIL_USER", "GMAIL_APP_PASSWORD",
                "GH_PAT"]:
        tests.append((f"ENV: {svc}", lambda k=svc: _test_env_var(k)))

    col1, col2 = st.columns([1, 1])
    with col1:
        st.button("Executar Todos os Testes", type="primary", use_container_width=True)
    with col2:
        clear = st.button("Limpar Resultados", use_container_width=True)
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
            if st.button("Testar", key=f"btn_{key}", use_container_width=True):
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

    with st.expander("📧  Testar SMTP (Gmail)", expanded=False):
        if not get_config("features.email.enabled", True):
            info_box("Email desabilitado em config/features.yaml", "warning")
        else:
            gmail_user = os.environ.get("GMAIL_USER", "")
            gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "")
            email_to = os.environ.get("ALERT_EMAIL_TO", "")
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("GMAIL_USER", value=gmail_user, key="diag_smtp_user")
                st.text_input("GMAIL_APP_PASSWORD", value=gmail_pass, type="password", key="diag_smtp_pass")
            with col2:
                st.text_input("ALERT_EMAIL_TO", value=email_to, key="diag_smtp_to")
            if st.button("Enviar Email de Teste", key="diag_btn_smtp", use_container_width=True):
                try:
                    import smtplib
                    from email.message import EmailMessage
                    msg = EmailMessage()
                    msg.set_content("Teste de envio CustoDoce - " + datetime.now().isoformat())
                    msg["Subject"] = "CustoDoce - Teste SMTP"
                    msg["From"] = gmail_user
                    msg["To"] = email_to
                    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
                        server.login(gmail_user, gmail_pass)
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
            if st.button("Enviar Mensagem de Teste", key="diag_btn_telegram", use_container_width=True):
                try:
                    import httpx
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


PAGE_HANDLERS = {
    "visao_geral": tab_visao_geral,
    "precos": tab_precos,
    "historico": tab_historico,
    "flyers": tab_flyers,
    "revisao": tab_revisao,
    "lojas": tab_lojas,
    "ingredientes": tab_ingredientes,
    "scrapers": tab_scrapers,
    "relatorios": tab_relatorios,
    "config": tab_config,
    "diagnostico": tab_diagnostico,
}


def main():
    if not require_auth():
        return

    plotly_theme()
    inject_css()
    render_sidebar()

    page = st.session_state.get("page", "visao_geral")
    handler = PAGE_HANDLERS.get(page)
    if handler:
        handler()
    else:
        st.error(f"Pagina desconhecida: {page}")


if __name__ == "__main__":
    main()
