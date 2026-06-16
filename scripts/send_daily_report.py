import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.price_service import get_latest_prices
from services.email_service import send_daily_report


def generate_report_html(prices: list[dict]) -> str:
    by_ingredient = {}
    for p in prices:
        ing = p.get("ingredient_id", "?")
        if ing not in by_ingredient:
            by_ingredient[ing] = []
        by_ingredient[ing].append(p)

    rows = ""
    for ing_name, items in sorted(by_ingredient.items()):
        best = min(items, key=lambda x: (
            (x.get("normalized") or {}).get("price_per_kg", 999999)
        ))
        norm = best.get("normalized") or {}
        price_kg = norm.get("price_per_kg", 0)

        rows += f"""
        <tr>
            <td><b>{ing_name}</b></td>
            <td>{best.get('store_name', '?')}</td>
            <td>R$ {best.get('raw_price', 0):.2f}</td>
            <td>R$ {price_kg:.2f}/kg</td>
            <td>{len(items)}</td>
        </tr>"""

    today = date.today().isoformat()
    html = f"""
    <html><head><meta charset="utf-8"></head><body>
    <h2>📊 CustoDoce - Relatório Diário</h2>
    <p>Data: {today} | Total de itens: {len(prices)}</p>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse">
        <tr style="background:#f0f0f0">
            <th>Ingrediente</th><th>Melhor Preço</th><th>Valor</th><th>R$/kg</th><th>Fontes</th>
        </tr>
        {rows}
    </table>
    <hr>
    <p><small>Enviado automaticamente pelo CustoDoce</small></p>
    </body></html>
    """
    return html


def main():
    prices = get_latest_prices()
    if not prices:
        print("Nenhum preço encontrado. Relatório não enviado.")
        return

    html = generate_report_html(prices)
    send_daily_report(report_html=html)
    print(f"Relatório diário enviado - {len(prices)} preços, {date.today()}")


if __name__ == "__main__":
    main()
