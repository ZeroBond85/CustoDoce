"""
validate_dashboard_queries.py

Valida que as queries usadas pelas paginas do dashboard
funcionam contra o Supabase real e retornam as colunas esperadas.

Uso:
    python scripts/validate_dashboard_queries.py

Exit code 0 se tudo OK, 1 se alguma validacao falhar.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REQUIRED_COLUMNS = {
    "prices": {
        "store_name",
        "raw_product",
        "raw_price",
        "raw_unit",
        "price_per_kg",
        "brand",
        "is_promotion",
        "valid_until",
        "collected_at",
        "normalized",
    },
    "price_history": {
        "ingredient_id",
        "store_name",
        "raw_price",
        "price_per_kg",
        "collected_at",
    },
    "ingredients": {
        "id",
        "canonical_name",
        "category",
        "active",
    },
    "stores": {
        "id",
        "name",
        "tier",
        "is_active",
    },
    "feature_flags": {
        "key",
        "enabled",
    },
    "scraping_logs": {
        "store_name",
        "status",
        "started_at",
    },
}


def check(description, ok, detail=""):
    icon = "[OK]" if ok else "[FAIL]"
    print(f"  {icon} {description}" + (f" - {detail}" if detail else ""))
    return ok


def validate_prices():
    from services.price_service import get_all_current_prices

    prices = get_all_current_prices(valid_only=True, limit=10)
    if not check("get_all_current_prices() retorna dados", len(prices) > 0, f"{len(prices)} rows"):
        return False
    cols = set(prices[0].keys())
    missing = REQUIRED_COLUMNS["prices"] - cols
    return check("Colunas de precos", not missing, f"faltando: {missing}" if missing else "")


def validate_search_prices():
    from services.price_service import search_prices

    prices = search_prices("Leite Condensado Integral", limit=5)
    if not check("search_prices() retorna dados", len(prices) > 0, f"{len(prices)} rows"):
        return False
    cols = set(prices[0].keys())
    missing = REQUIRED_COLUMNS["prices"] - cols
    return check("Colunas de search_prices", not missing, f"faltando: {missing}" if missing else "")


def validate_price_history():
    from services.price_service import get_price_history

    history = get_price_history("Leite Condensado Integral", days=7, valid_only=False)
    if not check("get_price_history() retorna dados", len(history) > 0, f"{len(history)} rows"):
        return False
    cols = set(history[0].keys())
    missing = REQUIRED_COLUMNS["price_history"] - cols
    return check("Colunas de price_history", not missing, f"faltando: {missing}" if missing else "")


def validate_cheapest_prices():
    from services.price_service import get_cheapest_prices

    cheapest = get_cheapest_prices("Leite Condensado Integral", top_n=3)
    if not check("get_cheapest_prices() retorna dados", len(cheapest) > 0, f"{len(cheapest)} rows"):
        return False
    cols = set(cheapest[0].keys())
    missing = REQUIRED_COLUMNS["prices"] - cols
    return check("Colunas de cheapest_prices", not missing, f"faltando: {missing}" if missing else "")


def validate_config_db_ingredients():
    from services.config_db import get_all_ingredients, get_active_ingredients

    all_ing = get_all_ingredients(include_inactive=True)
    if not check("get_all_ingredients() retorna dados", len(all_ing) > 0, f"{len(all_ing)} rows"):
        return False
    cols = set(all_ing[0].keys())
    missing = REQUIRED_COLUMNS["ingredients"] - cols
    ok = check("Colunas de ingredients", not missing, f"faltando: {missing}" if missing else "")

    active = get_active_ingredients()
    ok &= check("get_active_ingredients() retorna dados", len(active) > 0, f"{len(active)} rows")
    return ok


def validate_config_db_stores():
    from services.config_db import get_all_stores

    stores = get_all_stores(include_inactive=True)
    if not check("get_all_stores() retorna dados", len(stores) > 0, f"{len(stores)} rows"):
        return False
    cols = set(stores[0].keys())
    missing = REQUIRED_COLUMNS["stores"] - cols
    return check("Colunas de stores", not missing, f"faltando: {missing}" if missing else "")


def validate_feature_flags():
    from services.config_db import get_all_feature_flags

    flags = get_all_feature_flags()
    if not check("get_all_feature_flags() retorna dados", len(flags) > 0, f"{len(flags)} rows"):
        return False
    cols = set(flags[0].keys())
    missing = REQUIRED_COLUMNS["feature_flags"] - cols
    return check("Colunas de feature_flags", not missing, f"faltando: {missing}" if missing else "")


def validate_scraper_logs():
    from services.dashboard_queries import get_recent_scraper_logs

    logs = get_recent_scraper_logs(limit=5)
    if not check("get_recent_scraper_logs() retorna dados", len(logs) > 0, f"{len(logs)} rows"):
        return False
    cols = set(logs[0].keys())
    missing = REQUIRED_COLUMNS["scraping_logs"] - cols
    return check("Colunas de scraping_logs", not missing, f"faltando: {missing}" if missing else "")


def validate_dashboard_kpis():
    from services.dashboard_queries import get_dashboard_kpis

    kpis = get_dashboard_kpis()
    expected_keys = {"total_prices", "ingredients_covered", "stores_active", "avg_price_per_kg"}
    ok = True
    for key in expected_keys:
        ok &= check(f"KPI '{key}' presente", key in kpis, f"valor: {kpis.get(key, 'N/A')}")
    return ok


def validate_bot_commands():
    from services.config_db import get_active_ingredients

    ingredients = get_active_ingredients()
    if not check("Bot: get_active_ingredients() retorna dados", len(ingredients) > 0, f"{len(ingredients)} ativos"):
        return False
    names = [i.get("canonical_name", "") for i in ingredients]
    empty = [i for i, n in enumerate(names) if not n]
    return check("Bot: ingredientes tem canonical_name", len(empty) == 0, f"{len(empty)} sem nome" if empty else "ok")


def main():
    # Carregar .env antes de verificar env vars (falha local sem isso)
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description="Valida queries do dashboard contra Supabase real")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--skip-db-check", action="store_true", help="Pula verificacao de conexao inicial")
    args = parser.parse_args()

    os.environ.setdefault("SUPABASE_URL", "")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "")
    if not os.environ["SUPABASE_URL"] or not os.environ["SUPABASE_SERVICE_ROLE_KEY"]:
        print("[FAIL] SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY obrigatorios no .env")
        sys.exit(1)

    print("=" * 60)
    print("  Validacao de Queries do Dashboard (Supabase Real)")
    print("=" * 60)

    if not args.skip_db_check:
        print("\n>> Conexao Supabase...")
        from supabase import create_client

        c = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
        r = c.table("prices").select("id").limit(1).execute()
        assert r.data is not None, "Falha na conexao Supabase"
        print("  [OK] Conexao OK\n")

    results = []

    print(">> Prices...")
    results.append(validate_prices())

    print("\n>> Search Prices...")
    results.append(validate_search_prices())

    print("\n>> Price History...")
    results.append(validate_price_history())

    print("\n>> Cheapest Prices...")
    results.append(validate_cheapest_prices())

    print("\n>> Config DB: Ingredients...")
    results.append(validate_config_db_ingredients())

    print("\n>> Config DB: Stores...")
    results.append(validate_config_db_stores())

    print("\n>> Feature Flags...")
    results.append(validate_feature_flags())

    print("\n>> Scraper Logs...")
    results.append(validate_scraper_logs())

    print("\n>> Dashboard KPIs...")
    results.append(validate_dashboard_kpis())

    print("\n>> Bot Commands...")
    results.append(validate_bot_commands())

    total = len(results)
    passed = sum(results)
    failed = total - passed

    print("\n" + "=" * 60)
    print(f"  Resultado: {passed}/{total} passaram, {failed} falharam")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
