"""
Telegram Service - Simple message sending
"""

import os
import httpx


def send_telegram_message(chat_id: str, text: str) -> bool:
    """Send a simple message via Telegram Bot API."""
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN must be set")

    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            },
            timeout=15,
        )
        return response.status_code == 200
    except Exception:
        return False


def test_telegram_connection() -> tuple[bool, str]:
    """Test Telegram Bot API connection."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return False, "TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not configured"

    try:
        response = httpx.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10,
        )
        if response.status_code == 200:
            return True, "Telegram bot connected successfully"
        return False, f"API error: {response.text}"
    except Exception as e:
        return False, f"Connection error: {e}"
