"""
Price Analytics Service - Reports and data analysis.
"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from services.price_repository import get_latest_prices as get_all_current_prices
from services.supabase_client import get_supabase
from services.types import Ingredient, PriceEntry


def get_telegram_report(ingredients: list[Ingredient], top_n: int = 5) -> list[dict[str, Any]]:
    messages = []
    try:
        all_prices = get_all_current_prices(valid_only=True, limit=2000)
    except Exception:
        all_prices = []

    by_ing = defaultdict(list)
    for p in all_prices:
        by_ing[p.get("ingredient_id", "")].append(p)

    for ing in ingredients:
        name = ing["canonical_name"]
        prices = by_ing.get(name, [])
        valid = [
            p
            for p in prices
            if p.get("normalized") and isinstance(p["normalized"], dict) and p["normalized"].get("price_per_kg", 0) > 0
        ]
        valid.sort(key=lambda x: x["normalized"]["price_per_kg"])
        top = valid[:top_n]
        if top:
            messages.append({"ingredient": name, "prices": top})
    return messages


def get_longitudinal_winners(days: int = 90) -> list[dict[str, Any]]:
    """
    Identify stores that are consistently the cheapest over time.
    """
    client = get_supabase()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = (
        client.table("prices")
        .select("ingredient_id, store_name, raw_price, raw_unit, normalized, collected_at")
        .gte("collected_at", cutoff)
        .execute()
    )
    if not result.data:
        return []

    daily = defaultdict(lambda: defaultdict(list))
    for p in result.data:
        ing = p.get("ingredient_id", "")
        day = p.get("collected_at", "")[:10]
        raw_norm = p.get("normalized")
        norm = raw_norm if isinstance(raw_norm, dict) else {}
        ppk = norm.get("price_per_kg", 0) or 0
        if ppk <= 0:
            continue
        daily[ing][day].append({"store": p.get("store_name", "?"), "ppk": ppk})

    wins = defaultdict(lambda: defaultdict(int))
    for ing, days_dict in daily.items():
        for _day, entries in days_dict.items():
            if not entries:
                continue
            best = min(entries, key=lambda x: x["ppk"])
            wins[ing][best["store"]] += 1

    rows = []
    for ing, stores in wins.items():
        for store, count in stores.items():
            rows.append({"ingredient_id": ing, "store_name": store, "wins": count})
    rows.sort(key=lambda r: r["wins"], reverse=True)
    return rows


def get_price_trends(ingredient_id: str, days: int = 90) -> list[dict[str, Any]]:
    client = get_supabase()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = (
        client.table("prices")
        .select("store_name, raw_price, normalized, collected_at")
        .eq("ingredient_id", ingredient_id)
        .gte("collected_at", cutoff)
        .execute()
    )
    if not result.data:
        return []

    daily = defaultdict(list)
    for p in result.data:
        day = p.get("collected_at", "")[:10]
        raw_norm = p.get("normalized")
        norm = raw_norm if isinstance(raw_norm, dict) else {}
        ppk = norm.get("price_per_kg", 0) or 0
        if ppk > 0:
            daily[day].append(ppk)

    trends = []
    for day in sorted(daily):
        vals = daily[day]
        trends.append(
            {
                "date": day,
                "avg_ppk": round(sum(vals) / len(vals), 2),
                "min_ppk": round(min(vals), 2),
                "max_ppk": round(max(vals), 2),
                "store_count": len(vals),
            }
        )
    return trends


def get_cross_ingredient_ranking(days: int = 90) -> list[dict[str, Any]]:
    client = get_supabase()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = (
        client.table("prices")
        .select("ingredient_id, store_name, normalized, collected_at")
        .gte("collected_at", cutoff)
        .execute()
    )
    if not result.data:
        return []

    per_ing = defaultdict(list)
    for p in result.data:
        ing = p.get("ingredient_id", "")
        raw_norm = p.get("normalized")
        norm = raw_norm if isinstance(raw_norm, dict) else {}
        ppk = norm.get("price_per_kg", 0) or 0
        if ppk > 0:
            per_ing[ing].append({"store": p.get("store_name", "?"), "ppk": ppk})

    store_scores = defaultdict(lambda: {"top1": 0, "top3": 0, "total": 0})
    for _ing, entries in per_ing.items():
        sorted_entries = sorted(entries, key=lambda x: x["ppk"])
        seen = set()
        for rank, e in enumerate(sorted_entries, 1):
            if e["store"] in seen:
                continue
            seen.add(e["store"])
            store_scores[e["store"]]["total"] += 1
            if rank == 1:
                store_scores[e["store"]]["top1"] += 1
            if rank <= 3:
                store_scores[e["store"]]["top3"] += 1

    rows = []
    for store, scores in store_scores.items():
        rows.append(
            {
                "store_name": store,
                "top1_count": scores["top1"],
                "top3_count": scores["top3"],
                "total_ingredients": scores["total"],
            }
        )
    rows.sort(key=lambda r: (r["top1_count"], r["top3_count"]), reverse=True)
    return rows


def generate_report_html(products: list[PriceEntry], ingredients: list[Ingredient]) -> str:
    """Generates the HTML report for daily emails."""
    import html as _html
    from collections import defaultdict

    by_ingredient = defaultdict(list)
    for p in products:
        ing = p["ingredient_id"]
        if ing not in by_ingredient:
            by_ingredient[ing] = []
        by_ingredient[ing].append(p)

    rows = ""
    for ing_name, prices in sorted(by_ingredient.items()):
        best = min(
            prices,
            key=lambda x: (x.get("normalized") if isinstance(x.get("normalized"), dict) else {}).get(
                "price_per_kg", 999999
            ),
        )
        raw_norm = best.get("normalized")
        norm = raw_norm if isinstance(raw_norm, dict) else {}
        price_kg = norm.get("price_per_kg", 0)
        unique_stores = len({p.get("store_id", "") for p in prices})
        safe_ing = _html.escape(ing_name)
        safe_store = _html.escape(best["store_name"])
        rows += f"""
        <tr>
            <td><b>{safe_ing}</b></td>
            <td>{safe_store}</td>
            <td>R$ {best["raw_price"]:.2f}</td>
            <td>R$ {price_kg:.2f}/kg</td>
            <td>{unique_stores}</td>
        </tr>"""

    today = date.today().isoformat()
    html = f"""
    <html><body>
    <h2> CustoDoce - Relatorio Diario</h2>
    <p>Data: {today} | Total de itens: {len(products)}</p>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse">
        <tr style="background:#f0f0f0">
            <th>Ingrediente</th><th>Melhor Preco</th><th>Valor</th><th>R$/kg</th><th>Fontes</th>
        </tr>
        {rows}
    </table>
    <hr>
    <p><small>Enviado automaticamente pelo CustoDoce</small></p>
    </body></html>
    """
    return html


# ====================================================================
# Recurso 1 (RFC): Otimizador de Carrinho de Compras
# Compara dois cenários para a lista de compras da confeiteira:
#   - Monofonte: 1 loja que minimize o total
#   - Multifonte: dividir a compra em 1 ou 2 lojas para maior economia
# ====================================================================


def otimizar_carrinho_compras(lista_itens: dict, max_sources: int = 2) -> dict:
    """
    Analisa a lista de compras e calcula os cenários Monofonte e Multifonte.

    Args:
        lista_itens: {"<canonical_ingredient>": quantidade_kg (float), ...}
            quantidade_kg é quanto desse ingrediente a confeiteira precisa,
            em kg. Ex: {"Leite Condensado Integral": 5.0}
        max_sources: Quantas lojas podem ser combinadas em Multifonte (default 2).

    Returns:
        {
            "lista_faltando": [...],
            "cenario_monofonte": {"loja": str, "total": float, "itens": [...]},
            "cenario_multifonte": {"lojas": [...], "total": float, "economia": float, "itens": [...]},
            "format_markdown": str,
            "format_html": str,
        }
    """
    if not lista_itens:
        return {
            "lista_faltando": [],
            "cenario_monofonte": None,
            "cenario_multifonte": None,
            "format_markdown": "_Lista vazia_",
            "format_html": "<i>Lista vazia</i>",
        }

    try:
        latest_prices = get_all_current_prices(valid_only=True, limit=5000)
    except Exception:
        latest_prices = []

    # Index por (ingredient, store)
    by_ing_store: dict[str, dict[str, dict]] = defaultdict(dict)
    for p in latest_prices:
        ing = p.get("ingredient_id", "")
        sid = p.get("store_id") or p.get("store_name", "")
        raw_norm = p.get("normalized")
        norm = raw_norm if isinstance(raw_norm, dict) else {}
        ppk = norm.get("price_per_kg")
        if ing and sid and ppk and ppk > 0:
            by_ing_store[ing][sid] = {
                "store_id": sid,
                "store_name": p.get("store_name", "unknown"),
                "price_per_kg": float(ppk),
                "raw_price": p.get("raw_price"),
                "raw_unit": p.get("raw_unit"),
            }

    lista_faltando = []
    candidates = {}  # {ing: {store_id: price_per_kg}}
    for ing, _qty_kg in lista_itens.items():
        if ing not in by_ing_store or not by_ing_store[ing]:
            lista_faltando.append(ing)
            continue
        candidates[ing] = {sid: data["price_per_kg"] for sid, data in by_ing_store[ing].items()}

    if not candidates:
        return {
            "lista_faltando": lista_faltando,
            "cenario_monofonte": None,
            "cenario_multifonte": None,
            "format_markdown": "_Nenhum dos itens da lista tem preço coletado ainda._",
            "format_html": "<i>Nenhum dos itens da lista tem preço coletado ainda.</i>",
        }

    # Se há itens faltando, monofonte e multifonte não cobrem 100% da lista
    if lista_faltando:
        missing_str = ",".join(lista_faltando)
        return {
            "lista_faltando": lista_faltando,
            "cenario_monofonte": None,
            "cenario_multifonte": None,
            "format_markdown": "_Lista com " + str(len(lista_faltando)) + " item(ns) sem preço: " + missing_str,
            "format_html": "<i>Lista com itens faltando: " + missing_str + "</i>",
        }

    # =================================================================
    # Cenário Monofonte: para cada loja, soma o custo de TODOS os itens
    # =================================================================
    all_store_ids = set()
    for stores in candidates.values():
        all_store_ids.update(stores.keys())

    monofonte_per_store = []
    for sid in all_store_ids:
        covered = 0
        total = 0.0
        itens = []
        all_present = True
        for ing, store_prices in candidates.items():
            qty = float(lista_itens[ing])
            if sid in store_prices:
                price_pkg = store_prices[sid]
                cost = price_pkg * qty
                total += cost
                covered += 1
                itens.append(
                    {"ingredient": ing, "qty_kg": qty, "cost": cost, "price_per_kg": price_pkg, "store_id": sid}
                )
            else:
                all_present = False
                itens.append({"ingredient": ing, "qty_kg": qty, "cost": None, "store_id": sid})
        # Só considerar lojas que cobrem 100% da lista
        if all_present:
            monofonte_per_store.append(
                {
                    "store_id": sid,
                    "store_name": candidates
                    and next(
                        (by_ing_store[ing][sid].get("store_name", sid) for ing in candidates if sid in candidates[ing]),
                        sid,
                    ),
                    "total": total,
                    "itens": [it for it in itens if it["cost"] is not None],
                }
            )

    monofonte = None
    if monofonte_per_store:
        monofonte_per_store.sort(key=lambda x: x["total"])
        monofonte = monofonte_per_store[0]

    # =================================================================
    # Cenário Multifonte: top max_sources lojas que cobrem tudo
    # =================================================================
    multifonte = None
    if max_sources > 1:
        multifonte_per_combo: list[dict] = []

        # Para simplicidade O(n^2): combinação de até N=max_sources lojas
        from itertools import combinations

        store_ids_list = list(all_store_ids)
        for r in range(1, max_sources + 1):
            for combo in combinations(store_ids_list, r):
                # Verifica se combo cobre 100% da lista
                if not all(any(sid in candidates[ing] for sid in combo) for ing in candidates):
                    continue
                total = 0.0
                itens = []
                for ing in candidates:
                    qty = float(lista_itens[ing])
                    best_sid = min(combo, key=lambda sid: candidates[ing].get(sid, float("inf")))
                    price_pkg = candidates[ing][best_sid]
                    cost = price_pkg * qty
                    total += cost
                    itens.append(
                        {
                            "ingredient": ing,
                            "qty_kg": qty,
                            "cost": cost,
                            "price_per_kg": price_pkg,
                            "store_id": best_sid,
                        }
                    )
                multifonte_per_combo.append(
                    {
                        "store_ids": list(combo),
                        "store_names": list(
                            {
                                by_ing_store[ing][sid].get("store_name", sid)
                                for ing, sid in zip(
                                    candidates,
                                    [
                                        min(combo, key=lambda s: candidates[ing].get(s, float("inf")))
                                        for ing in candidates
                                    ],
                                    strict=False,
                                )
                                if sid in by_ing_store.get(ing, {})
                            }
                        ),
                        "total": total,
                        "itens": itens,
                    }
                )

        if multifonte_per_combo:
            multifonte_per_combo.sort(key=lambda x: x["total"])
            multifonte = multifonte_per_combo[0]

    # =================================================================
    # Formatting
    # =================================================================
    economia = None
    if multifonte and monofonte:
        economia = max(0.0, monofonte["total"] - multifonte["total"])

    md = _format_cart_md(lista_itens, lista_faltando, monofonte, multifonte)
    html = _format_cart_html(lista_itens, lista_faltando, monofonte, multifonte)

    return {
        "lista_faltando": lista_faltando,
        "cenario_monofonte": monofonte,
        "cenario_multifonte": multifonte,
        "economia_multifonte_vs_monofonte": economia,
        "format_markdown": md,
        "format_html": html,
    }


def _format_cart_md(itens, faltando, monofonte, multifonte) -> str:
    import io

    out = io.StringIO()
    out.write("🛒 *Carrinho de Compras (otimizado)*\n")
    out.write(f"  Itens solicitados: {len(itens)}\n")
    if faltando:
        out.write(f"  ⚠ Sem preço hoje: {', '.join(faltando)}\n")
    if monofonte:
        out.write(f"\n🏬 Monofonte: {monofonte['store_name']} → R$ {monofonte['total']:.2f}\n")
        for it in monofonte["itens"]:
            out.write(f"  - {it['ingredient']} {it['qty_kg']}kg (R${it['price_per_kg']:.2f}/kg) = R${it['cost']:.2f}\n")
    else:
        out.write("\n❌ Nenhuma loja cobre a lista inteira hoje.\n")
    if multifonte:
        if monofonte:
            out.write(
                f"\n🔀 Multifonte: cobertura com "
                f"{len(multifonte['store_names'])} lojas → "
                f"R$ {multifonte['total']:.2f}\n"
            )
        else:
            out.write(
                f"\n🔀 Multifonte (otimização por loja): "
                f"{len(multifonte['store_names'])} lojas → "
                f"R$ {multifonte['total']:.2f}\n"
            )
        for it in multifonte["itens"]:
            store_name = it.get("store_id", "?")  # Use store_id as default
            # Look up via items list - we don't have direct name mapping
            # Defaults to store_id if not found
            out.write(
                f"  - {it['ingredient']} {it['qty_kg']}kg @ "
                f"{store_name} "
                f"(R${it['price_per_kg']:.2f}/kg) = R${it['cost']:.2f}\n"
            )
    return out.getvalue()


def _format_cart_html(itens, faltando, monofonte, multifonte) -> str:
    import html as _html

    out = []
    out.append(
        f"<h3>🛒 Carrinho de Compras (otimizado)</h3>"
        f"<p>Itens: {len(itens)}. Quantidade total solicitada com base em kg.</p>"
    )
    if faltando:
        out.append(f"<p style='color:orange'>⚠ Sem preço hoje: {', '.join(_html.escape(f) for f in faltando)}</p>")
    if monofonte:
        rows = "".join(
            f"<tr><td>{_html.escape(it['ingredient'])}</td>"
            f"<td>{it['qty_kg']} kg</td>"
            f"<td>R$ {it['price_per_kg']:.2f}/kg</td>"
            f"<td>R$ {it['cost']:.2f}</td></tr>"
            for it in monofonte["itens"]
        )
        out.append(
            f"<h4>🏬 Cenário Monofonte: {_html.escape(monofonte['store_name'])}</h4>"
            f"<table border='1' cellpadding='6' style='border-collapse:collapse'>"
            f"<tr style='background:#f0f0f0'>"
            f"<th>Ingrediente</th><th>Qtd</th><th>R$/kg</th><th>Custo</th></tr>"
            f"{rows}"
            f"<tr style='background:#d0e8d0'><td colspan='3'><b>Total</b></td>"
            f"<td><b>R$ {monofonte['total']:.2f}</b></td></tr></table>"
        )
    if multifonte:
        rows = "".join(
            f"<tr><td>{_html.escape(it['ingredient'])}</td>"
            f"<td>{it['qty_kg']} kg</td>"
            f"<td>{_html.escape(it['store_id'])}</td>"
            f"<td>R$ {it['price_per_kg']:.2f}/kg</td>"
            f"<td>R$ {it['cost']:.2f}</td></tr>"
            for it in multifonte["itens"]
        )
        lojas_str = ", ".join(_html.escape(n) for n in multifonte["store_names"])
        out.append(
            f"<h4>🔀 Cenário Multifonte</h4>"
            f"<p>Lojas envolvidas: {lojas_str}</p>"
            f"<table border='1' cellpadding='6' style='border-collapse:collapse'>"
            f"<tr style='background:#f0f0f0'>"
            f"<th>Ingrediente</th><th>Qtd</th><th>Loja</th>"
            f"<th>R$/kg</th><th>Custo</th></tr>"
            f"{rows}"
            f"<tr style='background:#d0e8d0'><td colspan='4'><b>Total</b></td>"
            f"<td><b>R$ {multifonte['total']:.2f}</b></td></tr></table>"
        )
        if monofonte and multifonte["total"] < monofonte["total"]:
            economia = monofonte["total"] - multifonte["total"]
            out.append(f"<p style='color:green'><b>💰 Economia do Multifonte:</b> R$ {economia:.2f}</p>")
    return "\n".join(out)
