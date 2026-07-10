"""
services/scraper_alert.py

Notification alerts for scraper health events: auto-disable, critical scores,
and recovery. Wires into Telegram (primary) and email (fallback).

Gated by features.alerts.self_healing (default: true).
All API keys are optional — missing token degrades silently.
"""

import os

from services.config import get_feature
from services.logger import logger

# Default Telegram chat ID for health alerts
_DEFAULT_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("ALERT_CHAT_ID", "")


def notify_scraper_disabled(scraper_name: str, reason: str, failures_count: int) -> bool:
    if not get_feature("features.alerts.self_healing", default=True):
        return False
    msg = (
        f"⚠️ *Scraper Auto-Desativado*\n\n"
        f"Loja: `{scraper_name}`\n"
        f"Falhas consecutivas: {failures_count}\n"
        f"Motivo: {reason}\n\n"
        f"A reativação será avaliada em 15 dias pelo pipeline de auto-heal."
    )
    return _send_alert(msg)


def notify_health_critical(scraper_name: str, health_score: int) -> bool:
    if not get_feature("features.alerts.self_healing", default=True):
        return False
    msg = (
        f"🔴 *Saúde Crítica*\n\n"
        f"Loja: `{scraper_name}`\n"
        f"Health Score: {health_score}/100\n\n"
        f"Recomenda-se revisão manual."
    )
    return _send_alert(msg)


def notify_scraper_recovered(scraper_name: str) -> bool:
    if not get_feature("features.alerts.self_healing", default=True):
        return False
    msg = (
        f"🟢 *Scraper Recuperado*\n\n"
        f"Loja: `{scraper_name}` reativada automaticamente pelo pipeline de heal."
    )
    return _send_alert(msg)


def _send_alert(text: str) -> bool:
    chat_id = os.environ.get("SCRAPER_ALERT_CHAT_ID", _DEFAULT_CHAT_ID)
    if not chat_id:
        logger.debug("scraper_alert: no chat_id configured, skipping")
        return False
    try:
        from services.telegram_service import send_telegram_message
        return send_telegram_message(chat_id, text)
    except Exception as exc:
        logger.debug("scraper_alert: telegram failed (%s), trying email fallback", exc)
        return _send_email_fallback(text)


def _send_email_fallback(text: str) -> bool:
    try:
        from services.email_service import send_email

        recipient = os.environ.get("ALERT_EMAIL_TO", "")
        if not recipient:
            return False
        send_email(
            to=recipient,
            subject="[CustoDoce] Alerta de Scraper",
            body=text.replace("*", "").replace("`", ""),
        )
        return True
    except Exception as exc:
        logger.debug("scraper_alert: email fallback also failed (%s)", exc)
        return False
