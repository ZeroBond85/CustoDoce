"""Testa o scrape de UMA loja em isolamento, reutilizando 100% da orquestração real.

Uso:
    python scripts/test_single_store.py "<Store Name>" [max_seconds]

A loja é isolada via monkeypatch de ``collector.load_stores`` (retorna só ela),
então o método de coleta correspondente roda exatamente como no scrape regular
— incluindo self-healing, health recording e gravação no Supabase. Isso permite
validar uma loja específica sem disparar o scrape completo das outras.

Política de erro:
    - Erros transitórios (timeout, DNS, 429) NÃO desativam a loja nem disparam email.
    - Erros permanentes (layout, anti-bot) contam para o threshold de auto-disable.
"""

from __future__ import annotations

import json
import os
import sys
import traceback

os.environ.setdefault("CUSTODOCE_FORCE_SCRAPE", "1")

from services import collector
from services.config_db import get_store_by_name, get_active_stores

load_ingredients = collector.load_ingredients


def _resolve_method(store: dict):
    """Devolve a função de coleta do collector correspondente à loja."""
    scraper = store.get("scraper")
    stype = store.get("type")
    table = {
        "flyer_scraper": collector.collect_tier1_pdfs,
        "max_api_scraper": collector.collect_tier1_api_flyers,
        "extra_flyer_scraper": collector.collect_extra_flyers,
        "pao_flyer_scraper": collector.collect_pao_flyers,
        "roldao_flyer_scraper": collector.collect_roldao_flyer,
        "giga_flyer_scraper": collector.collect_giga_flyer,
        "vtex_scraper": collector.collect_tier2_vtex,
        "carrefour_scraper": collector.collect_carrefour,
        "playwright_price_scraper": collector.collect_tier2_js,
        "ecomplus_scraper": collector.collect_tier2_js,
        "website_scraper": collector.collect_tier3_websites,
        "aggregator_scraper": collector.collect_aggregators_ssr,
        "playwright_scraper": collector.collect_aggregators_js,
        "facebook_flyer_scraper": collector.collect_facebook_flyers,
    }
    if scraper in table:
        return table[scraper]
    # Fallbacks por tipo
    if stype in ("pdf_flyer",):
        return collector.collect_tier1_pdfs
    if stype in ("api_flyer",):
        return collector.collect_tier1_api_flyers
    raise ValueError(f"sem método de coleta para type={stype!r} scraper={scraper!r}")


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "uso: test_single_store.py '<Store Name>' [max_seconds]"}))
        return 2
    target = sys.argv[1]
    max_seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 900

    # Resolve direto no DB (get_store_by_name) — ignora o filtro scrape_frequencies.enabled
    # e o cap de 1000 linhas do PostgREST, então lojas pausadas/isoladas são encontradas.
    store = get_store_by_name(target)
    if store is None:
        available = [s.get("name") for s in get_active_stores()]
        print(json.dumps({"error": f"loja {target!r} não encontrada", "available": available}))
        return 2
    # Promove config jsonb (browse_urls, api_base, headers, ...) para o topo,
    # igual ao load_stores real — senão o scraper roda sem sua configuração.
    store = collector._merge_store_config(store)

    method = _resolve_method(store)

    # Isola a loja: o método de coleta filtra por type/scraper e usa load_stores().
    collector.load_stores = lambda: [store]

    ingredients = load_ingredients()
    result = {
        "store": target,
        "type": store.get("type"),
        "scraper": store.get("scraper"),
        "method": method.__name__,
        "ok": False,
        "collected": 0,
        "error": None,
    }
    try:
        import inspect

        # collect_aggregators_ssr/js não recebem ingredients (usam load_stores interno).
        takes_args = len(inspect.signature(method).parameters) > 0
        collected = method(ingredients) if takes_args else method()
        result["ok"] = True
        result["collected"] = len(collected) if isinstance(collected, list) else 0
    except Exception as exc:  # noqa: BLE001 - queremos capturar tudo no teste
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc(limit=5)

    # 0 produtos = falha real (timeout/rate-limit/site morto), nunca "sucesso".
    if result["ok"] and result["collected"] == 0:
        result["ok"] = False
        result["error"] = result["error"] or "0 produtos coletados (timeout/rate-limit/site indisponível)"

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
