import os

import yaml
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from services.price_service import get_prices_for_ingredient, get_latest_prices

INGREDIENTS_FILE = "config/ingredients.yaml"


def load_ingredients() -> list[dict]:
    with open(INGREDIENTS_FILE) as f:
        data = yaml.safe_load(f)
    return data.get("ingredients", [])


def format_price_entry(entry: dict, rank: int) -> str:
    norm = entry.get("normalized") or {}
    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "  ")
    price_kg = norm.get("price_per_kg", 0)
    price_un = norm.get("price_per_un", 0)
    store = entry.get("store_name", "?")
    product = entry.get("raw_product", "?")
    price = entry.get("raw_price", 0)
    unit = entry.get("raw_unit", "")

    line = f"{medal} <b>{store}</b>\n"
    line += f"   {product}: <b>R$ {price:.2f}</b>/{unit}\n"
    if price_kg > 0:
        line += f"   → <i>R$ {price_kg:.2f}/kg | R$ {price_un:.2f}/un</i>\n"
    return line


async def precos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text(
            "Use: /preco <ingrediente>\n"
            "Exemplo: /preco leite condensado\n\n"
            "Para ver todos os ingredientes: /lista"
        )
        return

    ingredients = load_ingredients()
    matched = None
    for ing in ingredients:
        if ing["canonical"].lower().startswith(query.lower()):
            matched = ing
            break

    if not matched:
        await update.message.reply_text(
            f"Ingrediente '{query}' não encontrado.\n"
            "Use /lista para ver todos."
        )
        return

    prices = get_prices_for_ingredient(matched["canonical"])
    if not prices:
        await update.message.reply_text(
            f"Nenhum preço encontrado para '{matched['canonical']}' ainda.\n"
            "Aguarde a próxima coleta."
        )
        return

    msg = f"🔍 <b>{matched['canonical']}</b> - {len(prices)} preços encontrados\n"
    msg += f"{'─' * 40}\n\n"

    for i, price in enumerate(prices[:10]):
        msg += format_price_entry(price, i + 1) + "\n"

    if len(prices) > 10:
        msg += f"...e mais {len(prices) - 10} preços. Use o dashboard para ver todos."

    await update.message.reply_text(msg, parse_mode="HTML")


async def lista_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ingredients = load_ingredients()
    categories = {}
    for ing in ingredients:
        cat = ing.get("category", "outros")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(ing["canonical"])

    msg = "📋 <b>Ingredientes Monitorados</b>\n\n"
    for cat, items in categories.items():
        msg += f"<b>{cat.upper()}</b>\n"
        for item in items:
            msg += f"  • {item}\n"
        msg += "\n"

    msg += (
        "Use /preco <nome> para ver os preços."
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = get_latest_prices()
    ingredients = load_ingredients()

    total = len(prices)
    stores = set(p.get("store_name") for p in prices)
    matched = len([p for p in prices if p.get("confidence", 0) >= 0.8])

    msg = (
        f"📊 <b>Status CustoDoce</b>\n\n"
        f"🕐 Última coleta: {prices[0]['collected_at'][:16] if prices else 'N/A'}\n"
        f"📦 Total de preços: {total}\n"
        f"🏪 Lojas com dados: {len(stores)}\n"
        f"✅ Preços confiáveis (≥80%): {matched}\n"
        f"🔬 Ingredientes monitorados: {len(ingredients)}\n"
        f"⚠️ Fila de revisão: ver no dashboard\n"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 <b>Bem-vindo ao CustoDoce!</b>\n\n"
        "🔍 Buscador de preços de ingredientes para confeitaria\n\n"
        "Comandos:\n"
        "/preco <ingrediente> - Ver preços (ex: /preco leite condensado)\n"
        "/lista - Ver todos os ingredientes monitorados\n"
        "/status - Status do sistema\n"
        "/ajuda - Ajuda\n\n"
        "📊 Dashboard completo: <a href='https://custodoce.streamlit.app'>custodoce.streamlit.app</a>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🆘 <b>Ajuda CustoDoce</b>\n\n"
        "<b>Como buscar preços:</b>\n"
        "/preco leite condensado\n"
        "/preco chocolate\n"
        "/preco nutella\n\n"
        "<b>Outros comandos:</b>\n"
        "/lista - Todos os ingredientes\n"
        "/status - Status do sistema\n\n"
        "<b>Dica:</b> você pode buscar pelo começo do nome.\n"
        "Ex: /preco choc encontra chocolate\n\n"
        "<b>Dashboard:</b> custodoce.streamlit.app"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


def run_bot():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN must be set.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("preco", precos_command))
    app.add_handler(CommandHandler("lista", lista_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("ajuda", help_command))
    app.add_handler(CommandHandler("help", help_command))

    app.run_polling()


if __name__ == "__main__":
    run_bot()
