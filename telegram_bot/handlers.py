import os
import logging

from rapidfuzz import fuzz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from services.price_service import get_prices_for_ingredient, get_latest_prices
from services.config_db import get_active_ingredients
from services.supabase_client import get_service_client

INGREDIENTS_FILE = "config/ingredients.yaml"
_PAGE_SIZE = 15

logger = logging.getLogger(__name__)


def load_ingredients() -> list[dict]:
    try:
        return get_active_ingredients()
    except Exception as e:
        logger.warning("DB ingredient load failed, falling back to YAML: %s", e)
        import yaml

        with open(INGREDIENTS_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("ingredients", [])


def _fuzzy_match(query: str, ingredients: list[dict]) -> list[tuple[dict, int]]:
    query_lower = query.lower()
    scored = []
    for ing in ingredients:
        name = ing.get("canonical_name", "")
        name_lower = name.lower()
        if query_lower in name_lower:
            scored.append((ing, 100 + len(query) - name_lower.index(query_lower)))
            continue
        score = fuzz.token_set_ratio(query_lower, name_lower)
        for alias in ing.get("aliases", []):
            alias_score = fuzz.token_set_ratio(query_lower, alias.lower())
            if alias_score > score:
                score = alias_score
        if score >= 60:
            scored.append((ing, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def format_price_entry(entry: dict, rank: int) -> str:
    raw_norm = entry.get("normalized")
    norm = raw_norm if isinstance(raw_norm, dict) else {}
    medal = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}.get(rank, "  ")
    price_kg = norm.get("price_per_kg", 0)
    price_un = norm.get("price_per_un", 0)
    store = entry.get("store_name", "?")
    product = entry.get("raw_product", "?")
    price = entry.get("raw_price", 0)
    unit = entry.get("raw_unit", "")

    line = f"{medal} <b>{store}</b>\n"
    line += f"   {product}: <b>R$ {price:.2f}</b>/{unit}\n"
    if price_kg > 0:
        line += f"   \u2192 <i>R$ {price_kg:.2f}/kg | R$ {price_un:.2f}/un</i>\n"
    return line


async def precos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text(
            "Use: /preco <ingrediente>\nExemplo: /preco leite condensado\n\nPara ver todos os ingredientes: /lista"
        )
        return

    ingredients = load_ingredients()
    matched_list = _fuzzy_match(query, ingredients)

    if not matched_list:
        await update.message.reply_text(f"Ingrediente '{query}' n\u00e3o encontrado.\nUse /lista para ver todos.")
        return

    matched = matched_list[0][0]
    prices = get_prices_for_ingredient(matched["canonical_name"])
    if not prices:
        await update.message.reply_text(
            f"Nenhum pre\u00e7o encontrado para '{matched['canonical_name']}' ainda.\nAguarde a pr\u00f3xima coleta."
        )
        return

    msg = f"\U0001f50d <b>{matched['canonical_name']}</b> - {len(prices)} pre\u00e7os\n"
    msg += "\u2500" * 40 + "\n\n"

    for i, price in enumerate(prices[:10]):
        msg += format_price_entry(price, i + 1) + "\n"

    if len(prices) > 10:
        msg += f"...e mais {len(prices) - 10} pre\u00e7os. Use o dashboard para ver todos."

    # If fuzzy match found alternatives, show them
    if len(matched_list) > 1:
        alt = matched_list[1:4]
        msg += "\n\n\U0001f4ac Voc\u00ea quis dizer:\n"
        for ing, _ in alt:
            msg += f"  /preco_{ing['canonical_name'].lower().replace(' ', '_')}\n"

    await update.message.reply_text(msg, parse_mode="HTML")


async def lista_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.replace("lista_page_", ""))
    await _send_lista_page(query.message.chat_id, page, context)


async def _send_lista_page(chat_id: int, page: int, context: ContextTypes.DEFAULT_TYPE):
    ingredients = load_ingredients()
    categories = {}
    for ing in ingredients:
        cat = ing.get("category", "outros")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(ing["canonical_name"])

    total_items = len(ingredients)
    total_pages = max(1, (total_items + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    cat_items = []
    for cat, items in categories.items():
        for item in items:
            cat_items.append((cat, item))

    start = page * _PAGE_SIZE
    end = start + _PAGE_SIZE
    page_items = cat_items[start:end]

    msg = f"\U0001f4cb <b>Ingredientes ({page + 1}/{total_pages})</b>\n\n"
    prev_cat = None
    for cat, item in page_items:
        if cat != prev_cat:
            msg += f"\n<b>{cat.upper()}</b>\n"
            prev_cat = cat
        msg += f"  \u2022 {item}\n"

    msg += "\nUse /preco <nome> para ver os pre\u00e7os."

    keyboard = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("\u25c0 Anterior", callback_data=f"lista_page_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Pr\u00f3ximo \u25b6", callback_data=f"lista_page_{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML", reply_markup=reply_markup)


async def lista_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_lista_page(update.effective_chat.id, 0, context)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ingredients = load_ingredients()
        prices = get_latest_prices()
    except Exception as e:
        await update.message.reply_text(f"Erro ao obter status: {e}")
        return

    total = len(prices)
    stores = {p.get("store_name") for p in prices}
    matched = len([p for p in prices if p.get("confidence", 0) >= 0.8])

    msg = (
        f"\U0001f4ca <b>Status CustoDoce</b>\n\n"
        f"\U0001f550 \u00daltima coleta: {prices[0]['collected_at'][:16] if prices else 'N/A'}\n"
        f"\U0001f4e6 Total de pre\u00e7os: {total}\n"
        f"\U0001f3ea Lojas com dados: {len(stores)}\n"
        f"\u2705 Pre\u00e7os confi\u00e1veis (\u226580%): {matched}\n"
        f"\U0001f52c Ingredientes monitorados: {len(ingredients)}\n"
        f"\u26a0 Fila de revis\u00e3o: ver no dashboard\n"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "\U0001f44b <b>Bem-vindo ao CustoDoce!</b>\n\n"
        "\U0001f50d Buscador de pre\u00e7os de ingredientes para confeitaria\n\n"
        "<b>Comandos:</b>\n"
        "/preco &lt;ingrediente&gt; - Ver pre\u00e7os (ex: /preco leite condensado)\n"
        "/lista - Ver todos os ingredientes monitorados\n"
        "/status - Status do sistema\n"
        "/ajuda - Ajuda\n\n"
        "\U0001f4ca Dashboard completo: <a href='https://custodoce.streamlit.app'>custodoce.streamlit.app</a>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "\U0001f198 <b>Ajuda CustoDoce</b>\n\n"
        "<b>Como buscar pre\u00e7os:</b>\n"
        "/preco leite condensado\n"
        "/preco chocolate\n"
        "/preco nutella\n\n"
        "<b>Outros comandos:</b>\n"
        "/lista - Todos os ingredientes\n"
        "/status - Status do sistema\n\n"
        "<b>Dica:</b> busca por qualquer parte do nome.\n"
        "Ex: /preco choc encontra chocolate em p\u00f3, chocolate nobre, etc.\n\n"
        "<b>Dashboard:</b> custodoce.streamlit.app"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def scrape_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text(
            "Use: /scrape <loja>\nExemplo: /scrape assai\n\nIsso solicitar\u00e1 uma coleta imediata desta loja."
        )
        return

    client = get_service_client()
    res = client.table("stores").select("id, name").ilike("name", f"%{query}%").execute()
    if not res.data:
        await update.message.reply_text(f"Loja '{query}' n\u00e3o encontrada.")
        return

    store = res.data[0]
    client.table("scrape_requests").insert(
        {"user_id": str(update.effective_user.id), "store_id": store["id"], "status": "pending"}
    ).execute()

    await update.message.reply_text(
        f"\u2705 Solicita\u00e7\u00e3o enviada para <b>{store['name']}</b>.\n"
        f"O rob\u00f4 coletar\u00e1 os pre\u00e7os na pr\u00f3xima execu\u00e7\u00e3o do worker (m\u00e1x 15 min)."
    )


def run_bot():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN must be set.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("preco", precos_command))
    app.add_handler(CommandHandler("lista", lista_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("scrape", scrape_command))
    app.add_handler(CommandHandler("ajuda", help_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(lista_callback, pattern=r"^lista_page_\d+$"))

    app.run_polling()


if __name__ == "__main__":
    run_bot()
