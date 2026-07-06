"""
Telegram Service - Simple message sending
"""

import os
from datetime import date

import httpx

from services.email_service import _load_stores


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


def _store_info_telegram(store_name: str) -> str:
    stores = _load_stores()
    info = stores.get(store_name, {})
    parts = []
    if info.get("address"):
        parts.append(f"\U0001f4cd {info['address']}")
    if info.get("phone"):
        parts.append(f"\U0001f4de {info['phone']}")
    if info.get("whatsapp"):
        parts.append(f"\U0001f4ac {info['whatsapp']}")
    if info.get("city") and not info.get("address"):
        parts.append(f"\U0001f3d9\ufe0f {info['city']}")
    if not parts:
        return ""
    return "   " + "  \u2022  ".join(parts)


def send_telegram_report(token: str, chat_id: str, ingredients: list[dict], prices_by_ingredient: dict):
    today = date.today().strftime("%d/%m/%Y")
    lines = ["\U0001f4ca *CustoDoce \u2014 Cotação de Preços*", f"\U0001f4c5 {today}\n"]
    n_with_prices = 0

    for ing in ingredients:
        name = ing["canonical_name"]
        prices = prices_by_ingredient.get(name, [])
        if not prices:
            continue

        best_per_store = {}
        for p in prices:
            store_id = p.get("store_id", p.get("store_name", "?"))
            raw_norm = p.get("normalized")
            norm = raw_norm if isinstance(raw_norm, dict) else {}
            ppk = norm.get("price_per_kg", 999999)
            if store_id not in best_per_store or ppk < best_per_store[store_id][0]:
                best_per_store[store_id] = (ppk, p)

        deduped = sorted(best_per_store.values(), key=lambda x: x[0])
        if not deduped:
            continue

        n_with_prices += 1
        best_entry = deduped[0]
        _, best_p = best_entry
        raw_best_norm = best_p.get("normalized")
        best_ppk = (raw_best_norm if isinstance(raw_best_norm, dict) else {}).get("price_per_kg", 0)

        lines.append(f"\U0001f3f7\ufe0f *{name}*")
        lines.append(f"   Melhor: R\\$ {best_ppk:.2f}/kg")

        for i, entry in enumerate(deduped[:5], 1):
            _, p = entry
            store = p.get("store_name", "?")
            raw_p = float(p.get("raw_price", 0))
            raw_norm = p.get("normalized")
            norm = raw_norm if isinstance(raw_norm, dict) else {}
            ppk = norm.get("price_per_kg", 0)
            unit = p.get("raw_unit", "")
            medal = ["\U0001f947", "\U0001f948", "\U0001f949"][i - 1] if i <= 3 else f"  {i}."
            promo = " \U0001f3f7\ufe0f" if p.get("is_promotion") else ""
            lines.append(f"{medal} {store}{promo}")
            info = _store_info_telegram(store)
            if info:
                lines.append(info)
            lines.append(f"   R\\$ {raw_p:.2f} {unit} \u2192 R\\$ {ppk:.2f}/kg")

        lines.append("")

    if not n_with_prices:
        lines.append("\u274c Nenhum preço encontrado hoje.")

    text = "\n".join(lines)
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        import logging
        _LOG = logging.getLogger(__name__)
        _LOG.warning("Falha ao enviar telegram: %s", exc)
        raise
