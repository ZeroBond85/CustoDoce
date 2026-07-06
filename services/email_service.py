import html as _html
import logging
import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from pathlib import Path

_LOG = logging.getLogger(__name__)

# ── Brand ( cores do logo CustoDoce ) ─────────────────────────────────
_BRAND = {
    "name": "CustoDoce",
    "primary": "#F59E42",  # laranja (Custo)
    "secondary": "#E91E8C",  # rosa (Doce)
    "accent": "#3B82F6",  # azul (cupcake icon)
    "bg": "#FFF9F5",
    "text": "#3D2C1E",
    "muted": "#8B7355",
    "light": "#9CA3AF",
    "white": "#FFFFFF",
    "danger": "#DC2626",
    "success": "#16A34A",
    "promo_bg": "#FDF2F8",  # rosa claro
    "promo_border": "#FBCFE8",  # rosa borda
    "promo_text": "#9D174D",  # rosa texto
}

_BASE_DIR = Path(__file__).resolve().parent.parent
_LOGO_PATH = _BASE_DIR / "Logocustodocepqueno.png"
_STORES_YAML = _BASE_DIR / "config" / "stores.yaml"


def _get_smtp_config():
    """Retorna config SMTP das env vars com fallback para Gmail."""
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or "587")
    user = os.environ.get("SMTP_USER") or os.environ.get("GMAIL_USER") or ""
    password = os.environ.get("SMTP_PASSWORD") or os.environ.get("GMAIL_APP_PASSWORD") or ""
    from_addr = os.environ.get("SMTP_FROM") or user
    return host, port, user, password, from_addr


def _logo_cid() -> str | None:
    """Retorna CID do logo se o arquivo existir, senão None."""
    if _LOGO_PATH.exists():
        return "logo"
    return None


# ── Store info cache ────────────────────────────────────────────────────
_STORES_CACHE: dict | None = None


def _load_stores() -> dict:
    """Carrega stores.yaml e retorna dict name -> {address, phone, whatsapp, city}."""
    global _STORES_CACHE
    if _STORES_CACHE is not None:
        return _STORES_CACHE
    import yaml

    if _STORES_YAML.exists():
        with open(_STORES_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        stores = {}
        for s in data.get("stores", []):
            name = s.get("name", "")
            units = s.get("units", [])
            addr = units[0].get("address", "") if units else ""
            phone = s.get("phone", "")
            whatsapp = s.get("whatsapp", "")
            city = s.get("cities", [""])[0] if s.get("cities") else ""
            stores[name] = {
                "address": addr,
                "phone": phone,
                "whatsapp": whatsapp,
                "city": city,
            }
        _STORES_CACHE = stores
        return stores
    _STORES_CACHE = {}
    return {}


def _store_info_html(store_name: str) -> str:
    """Retorna HTML com info da loja (endereço, telefone, whatsapp) se disponível."""
    stores = _load_stores()
    info = stores.get(store_name, {})
    parts = []
    if info.get("address"):
        parts.append(f"📍 {_html.escape(info['address'])}")
    if info.get("phone"):
        parts.append(f"📞 {_html.escape(info['phone'])}")
    if info.get("whatsapp"):
        parts.append(f"💬 WhatsApp: {_html.escape(info['whatsapp'])}")
    if info.get("city") and not info.get("address"):
        parts.append(f"🏙️ {_html.escape(info['city'])}")
    if not parts:
        return ""
    return (
        '<div style="margin-top:8px;padding:8px 12px;background:#F9FAFB;'
        'border-radius:6px;font-size:12px;color:#6B7280;line-height:1.6;">' + "<br>".join(parts) + "</div>"
    )


def _logo_tag() -> str:
    """Tag <img> para o logo (inline CID ou fallback texto)."""
    if _LOGO_PATH.exists():
        return (
            '<img src="cid:logo" alt="CustoDoce" class="logo-img" '
            'style="height:112px;width:auto;display:block;margin-bottom:8px;" '
            'width="auto">'
        )
    return (
        '<span style="font-size:28px;font-weight:700;">'
        f'<span style="color:{_BRAND["primary"]};">Custo</span>'
        f'<span style="color:{_BRAND["secondary"]};">Doce</span>'
        "</span>"
    )


def _tagline() -> str:
    """Tagline curta da empresa para o header do email."""
    return (
        '<p style="margin:2px 0 0 0;font-size:12px;color:rgba(255,255,255,0.85);">'
        "Compare precos de confeitaria e encontre as melhores ofertas da sua regiao."
        "</p>"
    )


def _wrap_html(title: str, preheader: str, body_inner: str) -> str:
    """Envelope HTML responsivo com preheader para clients de email."""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="format-detection" content="telephone=no,date=no,address=no,email=no,url=no">
<title>{_html.escape(title)}</title>
<!--[if mso]>
<noscript>
<xml>
<o:OfficeDocumentSettings>
<o:PixelsPerInch>96</o:PixelsPerInch>
</o:OfficeDocumentSettings>
</xml>
</noscript>
<![endif]-->
<style type="text/css">
/* Mobile-first responsive */
@media only screen and (max-width:480px){{
  table[class~=body-table] {{ width:100% !important; }}
  td[class~=body-cell] {{ padding:12px !important; }}
  td[class~=header-cell] {{ padding:16px 16px !important; }}
  img[class~=logo-img] {{ height:48px !important; }}
  h1[class~=email-h1] {{ font-size:18px !important; }}
  h2[class~=email-h2] {{ font-size:16px !important; }}
  p[class~=email-p] {{ font-size:14px !important; }}
  td[class~=table-th] {{ font-size:12px !important; padding:8px 6px !important; }}
  td[class~=table-td] {{ font-size:13px !important; padding:8px 6px !important; }}
  .table-wrap {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
}}
@media only screen and (max-width:640px){{
  .table-wrap {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
}}
</style>
</head>
<body style="margin:0;padding:0;background:{_BRAND["bg"]};font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:{_BRAND["text"]};-webkit-text-size-adjust:100%;">
<!-- preheader -->
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;">{_html.escape(preheader)}</div>
<!-- wrapper -->
<table class="body-table" role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BRAND["bg"]};">
<tr><td align="center" style="padding:24px 12px;" class="body-cell">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="max-width:640px;width:100%;background:{_BRAND["white"]};border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.06);">
  <!-- header -->
  <tr><td style="background:linear-gradient(135deg,{_BRAND["primary"]},{_BRAND["secondary"]});padding:20px 28px;" class="header-cell">
    {_logo_tag()}
    {_tagline()}
  </td></tr>
  <!-- body -->
  <tr><td style="padding:28px;" class="body-cell">
{body_inner}
  </td></tr>
  <!-- footer -->
  <tr><td style="padding:16px 28px;border-top:1px solid #F3F4F6;text-align:center;">
    <p style="margin:0;font-size:12px;color:{_BRAND["light"]};">
      Gerado automaticamente em {date.today().strftime("%d/%m/%Y")}. &mdash; CustoDoce
    </p>
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


# ── Relatório completo (email) ────────────────────────────────────────
def build_full_report_html(prices_by_ingredient: dict) -> str:
    """Gera relatório HTML responsivo - melhor preço por loja por ingrediente."""
    # Deduplica: melhor preço por loja por ingrediente
    deduped = {}
    for ing_name, prices in prices_by_ingredient.items():
        best_per_store = {}
        for p in prices:
            store_id = p.get("store_id", p.get("store_name", "?"))
            raw_norm = p.get("normalized")
            norm = raw_norm if isinstance(raw_norm, dict) else {}
            ppk = norm.get("price_per_kg", 999999)
            if store_id not in best_per_store or ppk < best_per_store[store_id][0]:
                best_per_store[store_id] = (ppk, p)
        deduped[ing_name] = [v[1] for v in best_per_store.values()]

    total = sum(len(v) for v in deduped.values())
    n_stores = len({p.get("store_id") for v in deduped.values() for p in v})

    sections = ""
    for ing_name, prices in sorted(deduped.items()):
        safe_ing = _html.escape(ing_name)
        sorted_prices = sorted(
            prices,
            key=lambda x: (x.get("normalized") if isinstance(x.get("normalized"), dict) else {}).get(
                "price_per_kg", 999999
            ),
        )
        best = sorted_prices[0] if sorted_prices else None
        raw_best_norm = best.get("normalized") if best else None
        best_ppk = (raw_best_norm if isinstance(raw_best_norm, dict) else {}).get("price_per_kg", 0) if best else 0
        best_store = _html.escape(best.get("store_name", "?")) if best else ""

        rows = ""
        for p in sorted_prices:
            store = _html.escape(p.get("store_name", "?"))
            product = _html.escape(p.get("raw_product", "?")[:45])
            raw_p = float(p.get("raw_price", 0))
            unit = p.get("raw_unit", "")
            raw_norm = p.get("normalized")
            norm = raw_norm if isinstance(raw_norm, dict) else {}
            ppk = norm.get("price_per_kg", 0)
            ppk_str = f"R$ {ppk:.2f}" if ppk else "—"
            promo = (
                " <span style='background:{};color:{};padding:2px 6px;border-radius:4px;font-size:11px;'>PROMO</span>".format(
                    _BRAND["promo_bg"], _BRAND["promo_text"]
                )
                if p.get("is_promotion")
                else ""
            )
            valid = p.get("valid_until", "")
            valid_str = f"<br><span style='font-size:11px;color:{_BRAND['light']}'>até {valid}</span>" if valid else ""
            highlight = "background:#FFFBEB;" if p == best else ""
            store_info = _store_info_html(p.get("store_name", ""))
            rows += f"""<tr style="{highlight}">
              <td class="table-td" style="padding:10px 12px;border-bottom:1px solid #F3F4F6;">{store}{promo}{valid_str}{store_info}</td>
              <td class="table-td" style="padding:10px 12px;border-bottom:1px solid #F3F4F6;font-size:13px;word-break:break-word;">{product}</td>
              <td class="table-td" style="padding:10px 12px;border-bottom:1px solid #F3F4F6;white-space:nowrap;">R$ {raw_p:.2f} {unit}</td>
              <td class="table-td" style="padding:10px 12px;border-bottom:1px solid #F3F4F6;white-space:nowrap;font-weight:600;">{ppk_str}</td>
            </tr>"""

        sections += f"""
        <div style="margin-bottom:24px;">
          <h2 class="email-h2" style="margin:0 0 4px 0;font-size:17px;color:{_BRAND["text"]};">{safe_ing}</h2>
          <p class="email-p" style="margin:0 0 10px 0;font-size:13px;color:{_BRAND["muted"]};">Melhor: {best_store} &mdash; R$ {best_ppk:.2f}/kg</p>
          <div class="table-wrap" style="overflow-x:auto;-webkit-overflow-scrolling:touch;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="border-collapse:collapse;background:{_BRAND["white"]};border-radius:8px;overflow:hidden;border:1px solid #F3F4F6;min-width:420px;">
            <thead>
              <tr style="background:{_BRAND["primary"]};color:{_BRAND["white"]};">
                <th class="table-th" style="padding:10px 12px;text-align:left;font-size:13px;">Loja</th>
                <th class="table-th" style="padding:10px 12px;text-align:left;font-size:13px;">Produto</th>
                <th class="table-th" style="padding:10px 12px;text-align:left;font-size:13px;">Preço</th>
                <th class="table-th" style="padding:10px 12px;text-align:left;font-size:13px;">R$/kg</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
          </div>
        </div>"""

    body = f"""
    <h1 class="email-h1" style="margin:0 0 4px 0;font-size:20px;color:{_BRAND["text"]};">Cotação de Preços</h1>
    <p class="email-p" style="margin:0 0 20px 0;font-size:14px;color:{_BRAND["muted"]};">
      {total} ofertas em {n_stores} lojas &mdash; {date.today().strftime("%d/%m/%Y")}
    </p>
    {sections}
    <p class="email-p" style="margin:20px 0 0 0;font-size:12px;color:{_BRAND["light"]};text-align:center;">
      Melhor preço por loja. Ordenado por R$/kg (menor primeiro). Destaque em amarelo.
    </p>"""
    return _wrap_html("Cotação CustoDoce", f"Cotação com {total} ofertas de {n_stores} lojas.", body)


# ── Alerta de oferta (email) ──────────────────────────────────────────
def send_critical_alert(
    ingredient_name: str,
    price: float,
    store: str,
    to_email: str | None = None,
):
    safe_name = _html.escape(ingredient_name)
    safe_store = _html.escape(store)
    body = f"""
    <h2 style="margin:0 0 16px 0;font-size:20px;color:{_BRAND["text"]};">🎯 Oferta Encontrada</h2>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background:{_BRAND["promo_bg"]};border-radius:8px;border:1px solid {_BRAND["promo_border"]};">
      <tr>
        <td style="padding:20px;">
          <p style="margin:0 0 6px 0;font-size:13px;color:{_BRAND["muted"]};">Ingrediente</p>
          <p style="margin:0 0 16px 0;font-size:18px;font-weight:700;color:{_BRAND["text"]};">{safe_name}</p>
          <p style="margin:0 0 6px 0;font-size:13px;color:{_BRAND["muted"]};">Preço</p>
          <p style="margin:0 0 16px 0;font-size:28px;font-weight:700;color:{_BRAND["secondary"]};">R$ {price:.2f}</p>
          <p style="margin:0 0 6px 0;font-size:13px;color:{_BRAND["muted"]};">Loja</p>
          <p style="margin:0;font-size:16px;font-weight:600;color:{_BRAND["text"]};">{safe_store}</p>
        </td>
      </tr>
    </table>"""
    send_daily_report(
        report_html=body,
        subject=f"🎯 Oferta: {ingredient_name} - R$ {price:.2f} em {store}",
        to_email=to_email,
    )


# ── Erro de scraper (email) ───────────────────────────────────────────
def send_scraper_error(store_name: str, error: str, to_email: str | None = None):
    safe_store = _html.escape(store_name)
    safe_error = _html.escape(error)
    body = f"""
    <h2 style="margin:0 0 16px 0;font-size:20px;color:{_BRAND["text"]};">⚠️ Erro no Scraper</h2>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background:#FEF2F2;border-radius:8px;border:1px solid #FECACA;">
      <tr>
        <td style="padding:20px;">
          <p style="margin:0 0 6px 0;font-size:13px;color:{_BRAND["muted"]};">Loja</p>
          <p style="margin:0 0 16px 0;font-size:18px;font-weight:700;color:{_BRAND["text"]};">{safe_store}</p>
          <p style="margin:0 0 6px 0;font-size:13px;color:{_BRAND["muted"]};">Erro</p>
          <p style="margin:0;font-size:14px;color:{_BRAND["danger"]};font-family:monospace;word-break:break-all;">{safe_error}</p>
        </td>
      </tr>
    </table>
    <p style="margin:16px 0 0 0;font-size:13px;color:{_BRAND["muted"]};">
      Verifique os <a href="https://github.com/ZeroBond85/CustoDoce/actions" style="color:{_BRAND["secondary"]};">logs do GitHub Actions</a>.
    </p>"""
    send_daily_report(
        report_html=body,
        subject=f"⚠️ Erro Scraper: {store_name}",
        to_email=to_email,
    )


# ── Envio genérico ────────────────────────────────────────────────────
def send_email(to_email: str, subject: str, html_body: str):
    """Simple email sender using the existing SMTP config."""
    host, port, user, password, from_addr = _get_smtp_config()

    if not user or not password or not to_email:
        raise ValueError("SMTP credentials not configured")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"CustoDoce <{from_addr}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if _LOGO_PATH.exists():
        with open(_LOGO_PATH, "rb") as f:
            img_data = f.read()
        img = MIMEImage(img_data, _subtype="png")
        img.add_header("Content-ID", "<logo>")
        img.add_header("Content-Disposition", "inline", filename="logo.png")
        msg.attach(img)

    if port == 465:
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=30)
        server.login(user, password)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(user, password)
    server.send_message(msg)
    server.quit()


def send_daily_report(
    report_html: str,
    csv_bytes: bytes | None = None,
    to_email: str | None = None,
    subject: str | None = None,
):
    host, port, user, password, from_addr = _get_smtp_config()
    to_email = to_email or os.environ.get("ALERT_EMAIL_TO", user)

    if not user or not password or not to_email:
        raise ValueError("SMTP_USER/SMTP_PASSWORD/ALERT_EMAIL_TO (ou GMAIL_USER/GMAIL_APP_PASSWORD) must be set.")

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject or f"📊 Cotação de Preços CustoDoce • {date.today().strftime('%d/%m/%Y')}"
    msg["From"] = f"CustoDoce <{from_addr}>"
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

    # Anexa logo como CID inline (se existir)
    if _LOGO_PATH.exists():
        with open(_LOGO_PATH, "rb") as f:
            img_data = f.read()
        img = MIMEImage(img_data, _subtype="png")
        img.add_header("Content-ID", "<logo>")
        img.add_header("Content-Disposition", "inline", filename="logo.png")
        msg.attach(img)

    if port == 465:
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=30)
        server.login(user, password)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(user, password)
    server.send_message(msg)
