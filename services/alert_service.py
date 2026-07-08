"""
Alert Service - Proactive notifications for price drops and system status.
"""

from datetime import UTC, datetime, timedelta

from services.email_service import send_email as send_email_notification
from services.logger import logger
from services.supabase_client import get_supabase
from services.telegram_service import send_telegram_message

# removed logger = logging.getLogger(__name__)


def get_active_alert_rules() -> list[dict]:
    client = get_supabase()
    return client.table("alert_rules").select("*").eq("enabled", True).execute().data or []


def get_alert_recipients(channel: str) -> list[dict]:
    client = get_supabase()
    return client.table("alert_recipients").select("*").eq("channel", channel).eq("active", True).execute().data or []


def check_price_drops(ingredient_id: str, current_price: float, history_prices: list[dict]) -> dict | None:
    """Check if the current price is a significant drop compared to history."""
    if not history_prices:
        return None

    # Get average of last 30 days
    prices = [
        p["normalized"]["price_per_kg"]
        for p in history_prices
        if p.get("normalized") and p["normalized"].get("price_per_kg", 0) > 0
    ]
    if not prices:
        return None

    avg_price = sum(prices) / len(prices)
    drop_pct = (avg_price - current_price) / avg_price

    if drop_pct >= 0.10:  # 10% drop
        return {"type": "price_drop", "drop_pct": drop_pct * 100, "old_avg": avg_price, "new_price": current_price}
    return None


def process_proactive_alerts():
    """
    Core loop to check all active rules and notify recipients.
    Should be called at the end of main.py.
    """
    logger.info("Checking proactive alerts...")
    rules = get_active_alert_rules()
    if not rules:
        return

    client = get_supabase()

    for rule in rules:
        trigger = rule["trigger"]

        # 1. Handle 'price_drop' trigger
        if trigger == "price_drop":
            # Find ingredients that just had a price update
            # For simplicity, we check the latest prices vs history
            latest = client.table("v_latest_prices").select("*").execute().data or []
            for p in latest:
                ing_id = p["ingredient_id"]
                current_ppk = p.get("price_per_kg", 0)
                if current_ppk <= 0:
                    continue

                # Get history for this ingredient
                hist = (
                    client.table("price_history")
                    .select("normalized")
                    .eq("ingredient_id", ing_id)
                    .order("collected_at", desc=True)
                    .limit(30)
                    .execute()
                    .data
                    or []
                )
                alert = check_price_drops(ing_id, current_ppk, hist)

                if alert:
                    msg = (
                        f"📉 <b>ALERTA DE PREÇO!</b>\n\n"
                        f"Ingrediente: {p['store_name']}\n"
                        f"Preço caiu {alert['drop_pct']:.1f}%!\n"
                        f"De: R$ {alert['old_avg']:.2f}/kg\n"
                        f"Para: <b>R$ {alert['new_price']:.2f}/kg</b>\n"
                        f"Loja: {p['store_name']}"
                    )
                    # Notify recipients for this rule's channel
                    channel = rule["channel"]
                    recs = get_alert_recipients(channel)
                    for r in recs:
                        if channel == "telegram":
                            send_telegram_message(r["target"], msg)
                        elif channel == "email":
                            send_email_notification(r["target"], "Alerta de Preço", msg)

        # 2. Handle 'scrape_failure' trigger
        elif trigger == "scrape_failure":
            # Check logs for errors in the last hour
            one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
            failures = (
                client.table("scraping_logs")
                .select("store_name,errors")
                .eq("status", "error")
                .gte("started_at", one_hour_ago)
                .execute()
                .data
                or []
            )

            if failures:
                msg = "⚠️ <b>FALHA NA COLETA</b>\n\nLojas com erro:\n"
                for f in failures:
                    msg += f"• {f['store_name']}\n"

                channel = rule["channel"]
                recs = get_alert_recipients(channel)
                for r in recs:
                    if channel == "telegram":
                        send_telegram_message(r["target"], msg)
                    elif channel == "email":
                        send_email_notification(r["target"], "Alerta de Sistema", msg)

    logger.info("Proactive alerts processed.")
