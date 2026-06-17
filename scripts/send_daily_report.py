import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.price_service import get_latest_prices
from services.email_service import send_daily_report, send_telegram_report, build_full_report_html
from services.config import get as get_config


def load_ingredients():
    import yaml
    with open("config/ingredients.yaml") as f:
        data = yaml.safe_load(f)
    return data.get("ingredients", [])


def main():
    prices = get_latest_prices(valid_only=True)

    if not prices:
        print("Nenhum preco vigente encontrado. Relatorio nao enviado.")
        return

    by_ingredient = {}
    for p in prices:
        ing = p.get("ingredient_id", "?")
        if ing not in by_ingredient:
            by_ingredient[ing] = []
        by_ingredient[ing].append(p)

    # --- EMAIL: full report (all prices, ASC per product) ---
    if get_config("features.email.full_report", True):
        html = build_full_report_html(by_ingredient)
        send_daily_report(report_html=html)
        print(f"Relatorio completo enviado - {len(prices)} precos")

    # --- TELEGRAM: top 5 cheapest per product ---
    if get_config("features.telegram.top5_report", True):
        token = __import__("os").environ.get("TELEGRAM_TOKEN")
        chat_id = __import__("os").environ.get("TELEGRAM_CHAT_ID")
        if token and chat_id:
            ingredients = load_ingredients()
            top5_by_ingredient = {}
            for ing in ingredients:
                name = ing["canonical"]
                ing_prices = sorted(
                    by_ingredient.get(name, []),
                    key=lambda x: (x.get("normalized") or {}).get("price_per_kg", 999999)
                )
                top5_by_ingredient[name] = ing_prices[:5]
            send_telegram_report(token, chat_id, ingredients, top5_by_ingredient)
            print(f"Relatorio Telegram enviado - {len(top5_by_ingredient)} ingredientes")
        else:
            print("TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID nao configurados. Pulando Telegram.")

    print(f"Relatorios enviados em {date.today()}")


if __name__ == "__main__":
    main()
