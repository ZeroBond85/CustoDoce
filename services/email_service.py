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
    msg["Subject"] = subject or f"CustoDoce - Relatorio Diario {date.today()}"
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
    <h2>Oferta Encontrada - CustoDoce</h2>
    <p><strong>{ingredient_name}</strong></p>
    <p>Preco: <strong>R$ {price:.2f}</strong></p>
    <p>Loja: {store}</p>
    <hr>
    <p><small>Enviado automaticamente pelo CustoDoce</small></p>
    </body></html>
    """
    send_daily_report(
        report_html=html,
        subject=f"Oferta: {ingredient_name} - R$ {price:.2f} em {store}",
        to_email=to_email,
    )


def send_scraper_error(store_name: str, error: str, to_email: Optional[str] = None):
    html = f"""
    <html><body>
    <h2>Erro no Scraper - CustoDoce</h2>
    <p><strong>Loja:</strong> {store_name}</p>
    <p><strong>Erro:</strong> {error}</p>
    <hr>
    <p><small>Verifique os logs do GitHub Actions.</small></p>
    </body></html>
    """
    send_daily_report(
        report_html=html,
        subject=f"Erro Scraper: {store_name}",
        to_email=to_email,
    )


def send_telegram_report(token: str, chat_id: str, ingredients: list[dict], prices_by_ingredient: dict):
    import httpx
    today = date.today().strftime("%d/%m/%Y")
    for ing_name, prices in prices_by_ingredient.items():
        if not prices:
            continue
        line = f"{today}\n\n{ing_name}\n"
        for i, p in enumerate(prices[:5], 1):
            store = p.get("store_name", "?")
            raw_p = float(p.get("raw_price", 0))
            norm = p.get("normalized") or {}
            ppk = norm.get("price_per_kg", 0)
            unit = p.get("raw_unit", "")
            promo = " [PROMO]" if p.get("is_promotion") else ""
            line += f"\n{i}. {store}{promo}\nR$ {raw_p:.2f} {unit} | R$ {ppk:.2f}/kg"
        line += "\n\n---"
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": line},
            timeout=15,
        )


def build_full_report_html(prices_by_ingredient: dict) -> str:
    hoje = date.today().strftime("%d/%m/%Y")
    sections = ""
    for ing_name, prices in sorted(prices_by_ingredient.items()):
        sorted_prices = sorted(prices, key=lambda x: (
            (x.get("normalized") or {}).get("price_per_kg", 999999)
        ))
        rows = ""
        for p in sorted_prices:
            store = p.get("store_name", "?")
            product = p.get("raw_product", "?")[:50]
            raw_p = float(p.get("raw_price", 0))
            unit = p.get("raw_unit", "")
            norm = p.get("normalized") or {}
            ppk = norm.get("price_per_kg", 0)
            ppk_str = f"R$ {ppk:.2f}/kg" if ppk else ""
            promo = " 🏷️" if p.get("is_promotion") else ""
            valid = p.get("valid_until", "")
            valid_str = f" (ate {valid})" if valid else ""
            rows += f"<tr><td>{store}{promo}</td><td>{product}</td><td>R$ {raw_p:.2f} {unit}</td><td>{ppk_str}</td><td>{valid_str}</td></tr>"
        sections += f"""
        <h3 style="color:#3D2C1E;margin-top:1.5rem;">{ing_name}</h3>
        <table style="width:100%;border-collapse:collapse;background:#FFF;border-radius:10px;overflow:hidden;margin-bottom:1rem;">
        <tr style="background:#F59E42;color:#FFF;"><th>Loja</th><th>Produto</th><th>Preco</th><th>R$/kg</th><th>Validade</th></tr>
        {rows}</table>"""

    return f"""<html><body style="font-family:Nunito,sans-serif;background:#FFF9F5;padding:20px;">
<h1 style="color:#F59E42;">CustoDoce - Relatorio Completo de Precos</h1>
<p style="color:#8B7355;">{hoje}</p>
{sections}
<p style="color:#9CA3AF;font-size:0.8rem;margin-top:20px;">Gerado automaticamente pelo CustoDoce</p>
</body></html>"""
