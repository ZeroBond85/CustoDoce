"""
Dashboard Page: Relatórios
"""

import streamlit as st
import pandas as pd
import os

from services.dashboard_queries import (
    get_latest_prices_cached,
)
from services.email_service import send_email
from services.telegram_service import send_telegram_message
from dashboard.components.ui import inject_css


def render_relatorios():
    inject_css()

    st.title("Relatórios & Alertas")

    tabs = st.tabs(["📧 Builder de Relatório", "📊 Preview", "🧪 Testar Envio"])

    with tabs[0]:  # Builder
        st.subheader("Montar Relatório Diário")

        col1, col2 = st.columns(2)
        with col1:
            _ = st.selectbox("Tipo", ["Diário (Top 5 por ingrediente)", "Semanal (Ranking)", "Personalizado"])
            _ = st.checkbox("Incluir promoções", value=True)
            _ = st.checkbox("Incluir tendências (7 dias)", value=False)
        with col2:
            recipients = st.multiselect("Destinatários", ["zerobond@gmail.com", "custodoce@gmail.com"])
            send_email_opt = st.checkbox("Enviar por Email", value=True)
            send_tg_opt = st.checkbox("Enviar por Telegram", value=True)

        if st.button("Gerar e Enviar Relatório", type="primary"):
            with st.spinner("Gerando relatório..."):
                html = build_daily_report_html()

                if send_email_opt and recipients:
                    for r in recipients:
                        send_email(r, "Relatório Diário CustoDoce", html)
                    st.success(f"Email enviado para {len(recipients)} destinatários")

                if send_tg_opt:
                    # Send summary via Telegram
                    summary = build_telegram_summary()
                    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
                    if chat_id:
                        send_telegram_message(chat_id, summary)
                    st.success("Telegram enviado")

                st.session_state["report_html"] = html
                st.rerun()

    with tabs[1]:  # Preview
        st.subheader("Preview do Relatório")

        if "report_html" in st.session_state:
            st.components.v1.html(st.session_state["report_html"], height=600, scrolling=True)
        else:
            html = build_daily_report_html()
            st.components.v1.html(html, height=600, scrolling=True)

    with tabs[2]:  # Testar
        st.subheader("Testar Envio")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("📧 Testar SMTP"):
                from services.email_service import test_smtp_connection

                with st.spinner("Testando..."):
                    ok, msg = test_smtp_connection()
                    if ok:
                        st.success("SMTP OK!")
                    else:
                        st.error(f"SMTP Falhou: {msg}")

        with col2:
            if st.button("📱 Testar Telegram"):
                from services.telegram_service import test_telegram_connection

                with st.spinner("Testando..."):
                    ok, msg = test_telegram_connection()
                    if ok:
                        st.success("Telegram OK!")
                    else:
                        st.error(f"Telegram Falhou: {msg}")


def build_daily_report_html() -> str:
    """Build HTML email report."""
    prices = get_latest_prices_cached(valid_only=True, limit=5000)

    if not prices:
        return "<p>Sem dados de preços.</p>"

    df = pd.DataFrame(prices)
    df["ppk"] = df.apply(lambda r: r.get("normalized", {}).get("price_per_kg", 0), axis=1)
    df = df[df["ppk"] > 0]

    # Top 5 por ingrediente
    top5 = df.sort_values("ppk").groupby("ingredient_id").head(5)

    html = """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            table { border-collapse: collapse; width: 100%; margin: 20px 0; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background: #ff6b35; color: white; }
            tr:nth-child(even) { background: #f9f9f9; }
            .header { background: linear-gradient(135deg, #ff6b35 0%, #ff9f1c 100%); color: white; padding: 20px; text-align: center; }
            .footer { text-align: center; color: #666; font-size: 12px; margin-top: 30px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🍰 CustoDoce - Relatório Diário</h1>
            <p>Top 5 menores preços por ingrediente</p>
        </div>
    """

    for ing in sorted(top5["ingredient_id"].unique()):
        ing_data = top5[top5["ingredient_id"] == ing]
        html += f"<h2>{ing}</h2>"
        html += "<table><tr><th>Loja</th><th>Produto</th><th>Preço</th><th>Unid.</th><th>R$/kg</th><th>Marca</th></tr>"
        for _, row in ing_data.iterrows():
            html += f"<tr><td>{row.get('store_name', '')}</td><td>{row.get('raw_product', '')}</td><td>R$ {row.get('raw_price', 0):.2f}</td><td>{row.get('raw_unit', '')}</td><td>R$ {row['ppk']:.2f}</td><td>{row.get('brand', '')}</td></tr>"
        html += "</table>"

    html += """
        <div class="footer">
            <p>CustoDoce - Comparação de preços para confeitaria</p>
            <p>Baixada Santista & São Paulo Capital</p>
        </div>
    </body>
    </html>
    """

    return html


def build_telegram_summary() -> str:
    """Build Telegram message summary."""
    prices = get_latest_prices_cached(valid_only=True, limit=5000)

    if not prices:
        return "🍰��� CustoDoce: Sem dados de preços hoje."

    df = pd.DataFrame(prices)
    df["ppk"] = df.apply(lambda r: r.get("normalized", {}).get("price_per_kg", 0), axis=1)
    df = df[df["ppk"] > 0]

    # Top 3 geral
    top3 = df.nsmallest(3, "ppk")

    msg = "🍰 *CustoDoce - Top 3 Ofertas do Dia*\n\n"
    for i, (_, row) in enumerate(top3.iterrows(), 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
        msg += f"{medal} *{row['ingredient_id']}*\n"
        msg += f"   {row['store_name']} - R$ {row['raw_price']:.2f}/{row['raw_unit']} (R$ {row['ppk']:.2f}/kg)\n"
        if row.get("brand"):
            msg += f"   Marca: {row['brand']}\n"
        msg += "\n"

    msg += "📊 Ver dashboard completo para mais detalhes."
    return msg


__all__ = ["render_relatorios"]
