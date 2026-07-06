"""
Dashboard Page: Relatórios
"""

import os

import pandas as pd
import streamlit as st

from dashboard.components.ui import inject_css
from services.dashboard_queries import (
    get_latest_prices_cached,
)
from services.email_service import send_email
from services.telegram_service import send_telegram_message


@st.dialog("Confirmar envio de relatório")
def _confirm_send_report_dialog(
    send_email_opt: bool,
    recipients: list,
    send_tg_opt: bool,
    report_kind: str,
):
    st.markdown(
        f"Você está prestes a enviar um relatório **{report_kind}**. "
        "Verifique o preview na aba lateral antes de continuar."
    )
    if send_email_opt and recipients:
        st.markdown(f"📧 **Email**: {len(recipients)} destinatário(s) — `{'`, `'.join(recipients)}`")
    if send_tg_opt:
        chat = os.environ.get("TELEGRAM_CHAT_ID", "(não definido)")
        st.markdown(f"📱 **Telegram**: chat_id `{chat}`")
    if not (send_email_opt or send_tg_opt):
        st.error("Nenhum canal de envio selecionado. Volta e marque Email ou Telegram.")
        return

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("❌ Cancelar", key="cancel_report_send", width="stretch"):
            st.rerun()
    with col2:
        if st.button(
            "📤 Enviar Relatório",
            key="confirm_report_send",
            type="primary",
            width="stretch",
        ):
            html = build_daily_report_html()
            errors: list[str] = []

            if send_email_opt and recipients:
                for r in recipients:
                    try:
                        send_email(r, "Relatório CustoDoce", html)
                    except Exception as e:
                        errors.append(f"email `{r}`: {e}")
                if not errors:
                    st.success(f"Email enviado para {len(recipients)} destinatário(s).")

            if send_tg_opt:
                chat_id = os.environ.get("TELEGRAM_CHAT_ID")
                if chat_id:
                    try:
                        summary = build_telegram_summary()
                        send_telegram_message(chat_id, summary)
                        st.success("Telegram enviado.")
                    except Exception as e:
                        errors.append(f"telegram: {e}")
                else:
                    errors.append("telegram: TELEGRAM_CHAT_ID não configurado")

            if errors:
                st.error("Falhas durante envio:")
                for err in errors:
                    st.write(f"- {err}")
            else:
                st.session_state["report_html"] = html
            st.rerun()


def render_relatorios():
    inject_css()

    st.title("Relatórios & Alertas")

    tabs = st.tabs(["📧 Builder de Relatório", "📊 Preview", "🧪 Testar Envio"])

    with tabs[0]:  # Builder
        st.subheader("Montar Relatório Diário")

        col1, col2 = st.columns(2)
        with col1:
            report_kind = st.selectbox(
                "Tipo",
                ["Diário (Top 5 por ingrediente)", "Semanal (Ranking)", "Personalizado"],
            )
            _ = st.checkbox("Incluir promoções", value=True)
            _ = st.checkbox("Incluir tendências (7 dias)", value=False)
        with col2:
            recipients = st.multiselect(
                "Destinatários",
                ["zerobond@gmail.com", "custodoce@gmail.com"],
            )
            send_email_opt = st.checkbox("Enviar por Email", value=True)
            send_tg_opt = st.checkbox("Enviar por Telegram", value=True)

        st.divider()
        if st.button("👀 Preview + Enviar", type="primary"):
            _confirm_send_report_dialog(
                send_email_opt=send_email_opt,
                recipients=recipients,
                send_tg_opt=send_tg_opt,
                report_kind=report_kind,
            )

    with tabs[1]:  # Preview
        st.subheader("Preview do Relatório")

        if "report_html" in st.session_state:
            st.components.v1.html(
                st.session_state["report_html"],
                height=600,
                scrolling=True,
            )
        else:
            with st.spinner("Gerando preview..."):
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


def _safe_ppk(r: dict) -> float:
    norm = r.get("normalized")
    if isinstance(norm, dict):
        try:
            return float(norm.get("price_per_kg", 0))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def build_daily_report_html() -> str:
    """Build HTML email report."""
    prices = get_latest_prices_cached(valid_only=True, limit=5000)

    if not prices:
        return "<p>Sem dados de preços.</p>"

    df = pd.DataFrame(prices)
    df["ppk"] = df.apply(_safe_ppk, axis=1)
    df = df[df["ppk"] > 0]

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
        return "🍰 CustoDoce: Sem dados de preços hoje."

    df = pd.DataFrame(prices)
    df["ppk"] = df.apply(_safe_ppk, axis=1)
    df = df[df["ppk"] > 0]

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
