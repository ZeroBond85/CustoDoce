import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import Optional


def send_daily_report(
    report_html: str,
    csv_bytes: Optional[bytes] = None,
    to_email: Optional[str] = None,
    subject: Optional[str] = None,
):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    to_email = to_email or os.environ.get("ALERT_EMAIL_TO", gmail_user)

    if not gmail_user or not gmail_password or not to_email:
        raise ValueError(
            "GMAIL_USER, GMAIL_APP_PASSWORD, and ALERT_EMAIL_TO must be set."
        )

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject or f"📊 CustoDoce - Relatório Diário {date.today()}"
    msg["From"] = f"CustoDoce Bot <{gmail_user}>"
    msg["To"] = to_email

    msg_alternative = MIMEMultipart("alternative")
    msg.attach(msg_alternative)

    msg_alternative.attach(MIMEText(report_html, "html", "utf-8"))

    if csv_bytes:
        msg.attach(
            MIMEApplication(
                csv_bytes,
                _subtype="csv",
                Name=f"precos_{date.today()}.csv",
            )
        )

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.send_message(msg)


def send_critical_alert(ingredient_name: str, price: float, store: str, to_email: Optional[str] = None):
    html = f"""
    <html><body>
    <h2>🔥 Oferta Encontrada - CustoDoce</h2>
    <p><strong>{ingredient_name}</strong></p>
    <p>Preço: <strong>R$ {price:.2f}</strong></p>
    <p>Loja: {store}</p>
    <hr>
    <p><small>Enviado automaticamente pelo CustoDoce</small></p>
    </body></html>
    """
    send_daily_report(
        report_html=html,
        subject=f"🔥 Oferta: {ingredient_name} - R$ {price:.2f} em {store}",
        to_email=to_email,
    )


def send_scraper_error(store_name: str, error: str, to_email: Optional[str] = None):
    html = f"""
    <html><body>
    <h2>⚠️ Erro no Scraper - CustoDoce</h2>
    <p><strong>Loja:</strong> {store_name}</p>
    <p><strong>Erro:</strong> {error}</p>
    <hr>
    <p><small>Verifique os logs do GitHub Actions.</small></p>
    </body></html>
    """
    send_daily_report(
        report_html=html,
        subject=f"⚠️ Erro Scraper: {store_name}",
        to_email=to_email,
    )
