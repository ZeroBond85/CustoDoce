"""
Alert Service - Proactive notifications for price drops and system status.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from services.email_service import is_email_configured, send_email as send_email_notification
from services.logger import logger
from services.supabase_client import get_supabase, safe_execute
from services.telegram_service import send_telegram_message


def get_active_alert_rules() -> list[dict[str, Any]]:
    client = get_supabase()
    return safe_execute(client.table("alert_rules").select("*").eq("enabled", True))


def get_alert_recipients(channel: str) -> list[dict[str, Any]]:
    client = get_supabase()
    return safe_execute(
        client.table("alert_recipients").select("*").eq("channel", channel).eq("active", True)
    )


def check_price_drops(ingredient_id: str, current_price: float, history_prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Check if the current price is a significant drop compared to history."""
    if not history_prices:
        return None

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


def process_proactive_alerts() -> None:
    """
    Core loop to check all active rules and notify recipients.
    Should be called at the end of main.py.
    """
    logger.info("Checking proactive alerts...")
    rules = get_active_alert_rules()
    if not rules:
        return

    client = get_supabase()
    email_configured = is_email_configured()
    if not email_configured:
        logger.warning("notification_skipped", channel="email", error="SMTP credentials not configured")

    for rule in rules:
        trigger = rule["trigger"]

        # 1. Handle 'price_drop' trigger
        if trigger == "price_drop":
            # Find ingredients that just had a price update
            latest = safe_execute(client.table("v_latest_prices").select("*"))
            if not latest:
                continue

            # Fix N+1: histórico de TODOS os ingredientes em UMA query
            ing_ids = list({p["ingredient_id"] for p in latest})
            hist_rows = safe_execute(
                client.table("price_history")
                .select("ingredient_id,normalized")
                .in_("ingredient_id", ing_ids)
                .order("collected_at", desc=True)
                .limit(min(len(ing_ids) * 30, 5000))
            )
            hist_by_ing: dict[str, list[dict[str, Any]]] = {}
            for h in hist_rows:
                ing_id = h.get("ingredient_id")
                if ing_id:
                    hist_by_ing.setdefault(ing_id, []).append(h)

            # Endereços das lojas em UMA query (para mensagem acionável)
            stores_map: dict[str, dict[str, Any]] = {}
            try:
                for s in safe_execute(client.table("stores").select("id,address,city")):
                    stores_map[s["id"]] = s
            except Exception as e:
                logger.warning("alert_stores_lookup_failed: %s", e)

            for p in latest:
                ing_id = p["ingredient_id"]
                current_ppk = p.get("price_per_kg", 0)
                if current_ppk <= 0:
                    continue

                alert = check_price_drops(ing_id, current_ppk, hist_by_ing.get(ing_id, [])[:30])

                if alert:
                    store_id = p.get("store_id")
                    store_info = stores_map.get(store_id, {}) if store_id else {}
                    addr = store_info.get("address") or ""
                    city = store_info.get("city") or ""
                    loc = f"{addr} — {city}" if addr and city else (addr or city)
                    brand = p.get("brand") or ""

                    # Fix: campo Ingrediente usava store_name (bug produção)
                    msg = (
                        f"📉 <b>ALERTA DE PREÇO!</b>\n\n"
                        f"Ingrediente: <b>{ing_id}</b>\n"
                        f"Produto: {p.get('raw_product', '')}\n"
                    )
                    if brand and brand.lower() not in ("desconhecido", ""):
                        msg += f"Marca: {brand}\n"
                    msg += (
                        f"Preço caiu {alert['drop_pct']:.1f}%!\n"
                        f"De: R$ {alert['old_avg']:.2f}/kg\n"
                        f"Para: <b>R$ {alert['new_price']:.2f}/kg</b>\n"
                        f"Loja: {p['store_name']}\n"
                    )
                    if loc:
                        msg += f"📍 {loc}\n"
                    if p.get("valid_until"):
                        msg += f"Válido até: {p['valid_until']}\n"

                    # Notify recipients for this rule's channel
                    channel = rule["channel"]
                    recs = get_alert_recipients(channel)
                    for r in recs:
                        try:
                            if channel == "telegram":
                                send_telegram_message(r["target"], msg)
                            elif channel == "email":
                                if not email_configured:
                                    continue
                                send_email_notification(r["target"], "Alerta de Preço", msg)
                        except Exception as notif_err:
                            logger.warning("notification_skipped", channel=channel, error=str(notif_err))

        # 2. Handle 'scrape_failure' trigger
        elif trigger == "scrape_failure":
            # Check logs for errors in the last hour
            one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
            failures = safe_execute(
                client.table("scraping_logs")
                .select("store_name,errors")
                .eq("status", "error")
                .gte("started_at", one_hour_ago)
            )

            if failures:
                msg = "⚠️ <b>FALHA NA COLETA</b>\n\nLojas com erro:\n"
                for f in failures:
                    msg += f"• {f['store_name']}\n"

                channel = rule["channel"]
                recs = get_alert_recipients(channel)
                for r in recs:
                    try:
                        if channel == "telegram":
                            send_telegram_message(r["target"], msg)
                        elif channel == "email":
                            if not email_configured:
                                continue
                            send_email_notification(r["target"], "Alerta de Sistema", msg)
                    except Exception as notif_err:
                        logger.warning("notification_skipped", channel=channel, error=str(notif_err))

    logger.info("Proactive alerts processed.")
