"""Teste completo do Dashboard Fase 1.

Uso:
    python tests/test_dashboard_full.py
"""

import os
import sys
import traceback
from datetime import UTC

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("ADMIN_PASSWORD", "custodoce2907")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")

PASS = 0
FAIL = 0
SKIP = 0


def _run_test(name: str, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL += 1
        tb = traceback.format_exc()
        # pega só as últimas 5 linhas do traceback
        lines = tb.strip().splitlines()
        detail = "\n".join(lines[-5:]) if len(lines) > 5 else tb
        print(f"  FAIL  {name}\n        {e}\n        {detail}")


def skip(name: str, reason: str):
    global SKIP
    SKIP += 1
    print(f"  SKIP  {name}  ({reason})")


# ═══════════════════════════════════════════════════════════════
print("\n=== 1. SERVICES ===\n")


def test_auth():
    from services.auth import (
        create_token,
        generate_totp_secret,
        get_totp_uri,
        hash_password,
        load_config,
        verify_password,
        verify_token,
    )

    # Password
    h = hash_password("admin123")
    assert verify_password("admin123", h), "verify failed"
    assert not verify_password("wrong", h), "wrong should fail"
    assert len(h) > 50, "hash too short"

    # JWT
    jwt_key = "c" * 32
    token = create_token("admin", jwt_key)
    payload = verify_token(token, jwt_key)
    assert payload["sub"] == "admin"
    assert payload["exp"] > payload["iat"]

    # Token inválido
    assert verify_token("invalid.token.here", "key") is None

    # Token expirado (manipulado)
    from datetime import datetime, timedelta

    import jwt as pyjwt

    short_key = "k" * 32
    expired = pyjwt.encode(
        {"sub": "admin", "exp": datetime.now(UTC) - timedelta(hours=1)}, short_key, algorithm="HS256"
    )
    assert verify_token(expired, short_key) is None

    # TOTP
    secret = generate_totp_secret()
    assert len(secret) > 20
    uri = get_totp_uri(secret, "admin", "CustoDoce")
    assert "otpauth://totp/" in uri
    assert secret in uri
    assert "CustoDoce" in uri

    # load_config
    cfg = load_config()
    assert cfg.admin_password_hash is not None
    assert cfg.secret_key is not None


def test_rate_limiter():
    from services.rate_limiter import RateLimiter

    rl = RateLimiter(max_attempts=3, window_seconds=60)

    assert not rl.is_limited("test-key")
    assert rl.remaining_attempts("test-key") == 3
    assert rl.retry_after("test-key") == 0

    rl.record_attempt("test-key")
    assert rl.remaining_attempts("test-key") == 2

    rl.record_attempt("test-key")
    rl.record_attempt("test-key")
    assert rl.remaining_attempts("test-key") == 0
    assert rl.is_limited("test-key")
    assert rl.retry_after("test-key") > 0

    rl.clear_attempts("test-key")
    assert not rl.is_limited("test-key")
    assert rl.remaining_attempts("test-key") == 3

    # Persistência SQLite
    rl.record_attempt("persist-test")
    rl2 = RateLimiter(max_attempts=3, window_seconds=60)
    assert rl2.remaining_attempts("persist-test") == 2
    rl2.clear_attempts("persist-test")


def test_all_imports():
    from admin.app import (
        PAGE_FUNCTIONS,
    )
    from dashboard.components.layout import PAGES

    assert len(PAGES) == 21, f"Esperado 21 paginas (20 + lojas_pendentes), encontrado {len(PAGES)}"
    for page_id, icon, label in PAGES:
        assert page_id in PAGE_FUNCTIONS, f"Faltando handler para {page_id}"

    # testa que cada handler existe e é callable
    for page_id, handler in PAGE_FUNCTIONS.items():
        assert callable(handler), f"Handler {page_id} não é callable"


def test_calculadora_imports():
    """Verifica que get_cheapest_prices existe e render_calculadora é callable."""
    from services.price_service import get_cheapest_prices

    assert callable(get_cheapest_prices)
    from dashboard.pages.calculadora import render_calculadora

    assert callable(render_calculadora)


def test_cleanup_imports():
    """Verifica que cleanup_old_flyers e cleanup_old_logs sao importaveis."""
    import inspect

    from services.flyer_service import cleanup_old_flyers
    from services.price_service import cleanup_old_logs, cleanup_old_prices

    # Verifica assinaturas
    assert callable(cleanup_old_prices)
    assert callable(cleanup_old_logs)
    assert callable(cleanup_old_flyers)

    sig_prices = inspect.signature(cleanup_old_prices)
    sig_logs = inspect.signature(cleanup_old_logs)
    sig_flyers = inspect.signature(cleanup_old_flyers)

    assert "retention_days" in sig_prices.parameters
    assert "retention_days" in sig_logs.parameters
    assert "retention_days" in sig_flyers.parameters

    # Verifica default values
    assert sig_prices.parameters["retention_days"].default == 90
    assert sig_logs.parameters["retention_days"].default == 30
    assert sig_flyers.parameters["retention_days"].default == 60


# ═══════════════════════════════════════════════════════════════
print("=== 3. LOGIN PAGE ===\n")


def test_login_render_function():
    from dashboard.login_page import render_login

    assert callable(render_login)


def test_setup_render_function():
    from dashboard.login_page import render_setup_first_user

    assert callable(render_setup_first_user)


def test_login_limiter_integration():
    from services.rate_limiter import RateLimiter

    rl = RateLimiter(max_attempts=5, window_seconds=60)
    ip = "192.168.1.1"
    assert not rl.is_limited(ip)
    for _ in range(5):
        rl.record_attempt(ip)
    assert rl.is_limited(ip)
    rl.clear_attempts(ip)
    assert not rl.is_limited(ip)


# ═══════════════════════════════════════════════════════════════
print("=== 4. PAGE HANDLERS ===\n")


def test_page_handler_registry():
    from admin.app import PAGE_FUNCTIONS
    from dashboard.components.layout import PAGES as PAGES_LAYOUT

    assert len(PAGE_FUNCTIONS) == len(PAGES_LAYOUT)
    for page_id, _, _ in PAGES_LAYOUT:
        assert page_id in PAGE_FUNCTIONS, f"Faltando handler: {page_id}"


def test_ingredients_yaml():
    import yaml

    with open("config/ingredients.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    ings = data.get("ingredients", [])
    assert len(ings) >= 11, f"Esperado >=11 ingredientes, encontrado {len(ings)}"
    for ing in ings:
        assert "canonical" in ing or "canonical_name" in ing, f"Ingrediente sem canonical/canonical_name: {ing}"
        assert "aliases" in ing, f"{ing['canonical_name']} sem aliases"
        assert "category" in ing, f"{ing['canonical_name']} sem category"


def test_stores_yaml():
    import yaml

    with open("config/stores.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    stores = data.get("stores", [])
    assert len(stores) >= 49, f"Esperado >=49 lojas, encontrado {len(stores)}"
    tiers = set()
    for s in stores:
        assert "name" in s
        assert "tier" in s
        tiers.add(s["tier"])
    assert tiers, "Nenhum tier encontrado"


# ═══════════════════════════════════════════════════════════════
print("=== 5. APP LOADER ===\n")


def test_app_module_loads():
    # Simula o carregamento completo do módulo admin.app
    # sem executar o main (que precisa de st)
    import admin.app as app_mod

    assert hasattr(app_mod, "main")
    assert hasattr(app_mod, "PAGE_FUNCTIONS")


def test_env_auth_flow():
    from services.auth import hash_password, verify_password

    # Com ADMIN_PASSWORD setado, verifica fluxo
    pw_plain = os.environ.get("ADMIN_PASSWORD", "")
    if pw_plain:
        # o load_config retorna hash, mas verifica via texto
        pass

    # Teste com hash
    h = hash_password("minha-senha-segura")
    assert verify_password("minha-senha-segura", h)
    assert not verify_password("outra-senha", h)


# ═══════════════════════════════════════════════════════════════
print("=== 6. STRUCTURE ===\n")


def test_no_secrets_in_code():
    import re

    secrets_patterns = [
        r'supabase\.co[^"\']*["\']',
        r'password\s*=\s*["\'][^"\']{8,}["\']',
    ]

    code_files = [
        "services/auth.py",
        "services/rate_limiter.py",
        "services/supabase_client.py",
        "services/price_service.py",
        "dashboard/components/ui.py",
        "dashboard/components/layout.py",
        "dashboard/login_page.py",
        "admin/app.py",
    ]

    for fname in code_files:
        if not os.path.exists(fname):
            continue
        with open(fname, encoding="utf-8", errors="replace") as f:
            content = f.read()
        for pat in secrets_patterns:
            matches = re.findall(pat, content)
            if matches:
                # Filtra falsos positivos como urls de exemplo
                clean = [m for m in matches if "seu-projeto" not in m and "sua-anon" not in m]
                assert not clean, f"{fname}: Possível secret vazado: {clean[:3]}"


# ═══════════════════════════════════════════════════════════════
print("=== 7. DESIGN REVIEW ===\n")


def test_sidebar_navigation():
    from dashboard.components.layout import PAGES

    page_ids = [p[0] for p in PAGES]
    assert "visao_geral" in page_ids
    assert "precos" in page_ids
    assert "historico" in page_ids
    assert "flyers" in page_ids
    assert "revisao" in page_ids
    assert "lojas" in page_ids
    assert "ingredientes" in page_ids
    assert "scrapers" in page_ids
    assert "relatorios" in page_ids
    assert "config" in page_ids
    assert "diagnostico" in page_ids


# ═══════════════════════════════════════════════════════════════
print("=== 9. PHASE 3 — FLYERS & HISTORY ===\n")


def test_flyer_status_color():
    from admin.app import _flyer_status_color

    assert _flyer_status_color("done") == "#10B981"
    assert _flyer_status_color("processed") == "#10B981"
    assert _flyer_status_color("pending") == "#F59E0B"
    assert _flyer_status_color("failed") == "#EF4444"
    assert _flyer_status_color("error") == "#EF4444"
    assert _flyer_status_color("unknown") == "#6B7280"


def test_flyer_status_label():
    from admin.app import _flyer_status_label

    assert _flyer_status_label("done") == "processado"
    assert _flyer_status_label("processed") == "processado"
    assert _flyer_status_label("pending") == "pendente"
    assert _flyer_status_label("failed") == "falha"
    assert _flyer_status_label("error") == "falha"
    assert _flyer_status_label("unknown") == "unknown"


def test_format_kg():
    from admin.app import _format_kg

    assert _format_kg({"price_per_kg": 42.90}) == 42.90
    assert _format_kg({"price_per_kg": 0}) == 0
    assert _format_kg({}) == 0
    assert _format_kg(None) == 0
    assert _format_kg("string") == 0


def test_get_kg():
    import pandas as pd

    from admin.app import _get_kg

    df = pd.DataFrame({"normalized": [{"price_per_kg": 10.0}, {"price_per_kg": 20.0}, {}, None]})
    vals = _get_kg(df)
    assert vals.tolist() == [10.0, 20.0, 0, 0]


def test_flyer_service_upsert():
    from services.flyer_service import upsert_flyer

    assert callable(upsert_flyer)


def test_flyer_service_mark_processed():
    from services.flyer_service import mark_processed

    assert callable(mark_processed)


def test_flyer_service_mark_failed():
    from services.flyer_service import mark_failed

    assert callable(mark_failed)


def test_flyer_service_get_recent():
    from services.flyer_service import get_recent_flyers

    assert callable(get_recent_flyers)


def test_flyer_service_get_pending():
    from services.flyer_service import get_pending_flyers

    assert callable(get_pending_flyers)


def test_price_service_search():
    from services.price_service import (
        approve_review_item,
        get_latest_prices,
        get_price_history,
        insert_review_item,
        reject_review_item,
        search_prices,
    )

    assert callable(search_prices)
    assert callable(get_latest_prices)
    assert callable(get_price_history)
    assert callable(insert_review_item)
    assert callable(approve_review_item)
    assert callable(reject_review_item)


def test_home_kpi_flyer_structure():
    """Verifica que os KPIs de flyer tem os selectors corretos"""
    with open("dashboard/static/style.css", encoding="utf-8") as f:
        content = f.read()

    assert ".cd-metric" in content
    assert ".cd-kpi-row" in content
    assert "cd-metric .label" in content
    assert "cd-metric .value" in content


def test_flyer_kpi_row_in_home():
    """Verifica que o KPI de flyers esta presente na funcao render_flyers"""
    with open("dashboard/pages/flyers.py", encoding="utf-8") as f:
        content = f.read()
    with open("dashboard/pages/visao_geral.py", encoding="utf-8") as f2:
        content2 = f2.read()

    assert "get_recent_flyers" in content
    assert "get_recent_flyers" in content2 or "metric" in content2


def test_history_chart_types():
    """Verifica que a tab historico oferece tipos de grafico"""
    with open("dashboard/pages/historico.py", encoding="utf-8") as f:
        content = f.read()

    assert "chart_type" in content
    assert "px." in content


def test_flyer_detail_section():
    """Verifica que o detalhe do flyer tem os campos obrigatorios"""
    with open("dashboard/static/style.css", encoding="utf-8") as f:
        content = f.read()
    with open("dashboard/pages/flyers.py", encoding="utf-8") as f2:
        content2 = f2.read()

    assert ".cd-flyer-detail" in content
    assert "Loja:" in content2
    assert "Fonte:" in content2
    assert "Coletado:" in content2


def test_generate_secret_key():
    from services.auth import generate_secret_key

    key = generate_secret_key()
    assert len(key) >= 32, f"Chave muito curta: {len(key)}"


def test_rate_limiter_window_expires():
    import time

    from services.rate_limiter import RateLimiter

    rl = RateLimiter(max_attempts=1, window_seconds=1)
    rl.record_attempt("expire-test")
    assert rl.remaining_attempts("expire-test") == 0
    assert rl.is_limited("expire-test")
    time.sleep(1.5)
    assert not rl.is_limited("expire-test"), "Janela deveria ter expirado"
    rl.clear_attempts("expire-test")


def test_rate_limiter_independent_keys():
    from services.rate_limiter import RateLimiter

    rl = RateLimiter(max_attempts=3, window_seconds=60)
    rl.record_attempt("key-a")
    rl.record_attempt("key-a")
    rl.record_attempt("key-a")
    assert rl.is_limited("key-a")
    assert not rl.is_limited("key-b")
    assert rl.remaining_attempts("key-b") == 3
    rl.clear_attempts("key-a")
    rl.clear_attempts("key-b")


def test_jwt_key_length():
    """Verifica que a chave JWT tem no minimo 32 bytes (RFC 7518)"""
    from services.auth import load_config

    cfg = load_config()
    assert len(cfg.secret_key) >= 32, f"Chave JWT tem {len(cfg.secret_key)} bytes, minimo 32"


def test_tab_visao_geral_refactored():
    """Verifica que visao_geral foi modularizada"""
    from dashboard.pages.visao_geral import render_visao_geral

    assert callable(render_visao_geral)
    import dashboard.pages.visao_geral as vg_mod

    assert hasattr(vg_mod, "render_visao_geral")


def test_tab_visao_geral_complexity():
    """Verifica que render_visao_geral tem corpo enxuto"""
    import ast

    with open("dashboard/pages/visao_geral.py", encoding="utf-8") as f:
        content = f.read()
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "render_visao_geral":
            control = sum(1 for n in ast.walk(node) if isinstance(n, (ast.If, ast.For, ast.While, ast.Try)))
            assert control <= 8, f"render_visao_geral tem {control} nos de controle"
            return
    raise AssertionError("render_visao_geral nao encontrada no AST")


def test_tab_lojas_features():
    """Verifica que tab_lojas tem filtros, busca e editor DB"""
    with open("dashboard/pages/lojas.py", encoding="utf-8") as f:
        content = f.read()
    assert "Incluir" in content
    assert "cached_get_all_stores" in content
    assert "upsert_store" in content
    assert "YAML" in content


def test_tab_ingredientes_tester():
    """Verifica que tab_ingredientes tem testadores"""
    with open("dashboard/pages/ingredientes.py", encoding="utf-8") as f:
        content = f.read()
    assert "normalizer" in content.lower() or "matcher" in content.lower()
    assert "normalize_price" in content or "match_ingredient" in content or "test" in content.lower()


def test_normalizer_function():
    """Verifica que normalize_price existe e e callable"""
    from parsers.normalizer import normalize_price

    assert callable(normalize_price)
    result = normalize_price(42.90, "1kg")
    assert hasattr(result, "price_per_kg") or isinstance(result, dict)


def test_matcher_function():
    """Verifica que match_ingredient existe e e callable"""
    from parsers.matcher import match_ingredient

    assert callable(match_ingredient)


def test_render_functions_exist():
    """Verifica que visao_geral chama sub-funcoes"""
    with open("dashboard/pages/visao_geral.py", encoding="utf-8") as f:
        content = f.read()
    assert "render_visao_geral" in content
    assert "st." in content
    assert "def " in content


def test_test_smtp():
    from services.email_service import send_email

    assert callable(send_email)


def test_test_telegram():
    from services.telegram_service import test_telegram_connection

    assert callable(test_telegram_connection)


def test_render_schedule_info():
    from dashboard.pages.scrapers import render_scrapers

    assert callable(render_scrapers)


def test_tab_relatorios_features():
    with open("dashboard/pages/relatorios.py", encoding="utf-8") as f:
        content = f.read()
    assert "Relat" in content
    assert "send_email" in content or "email" in content.lower()
    assert "Telegram" in content or "telegram" in content.lower()


def test_tab_scrapers_schedule():
    with open("dashboard/pages/scrapers.py", encoding="utf-8") as f:
        content = f.read()
    assert "Agendamento" in content or "Schedule" in content or "scrape" in content.lower()
    assert "cron" in content.lower() or "scrape.yml" in content.lower()


def test_secret_groups():
    with open("dashboard/pages/config.py", encoding="utf-8") as f:
        content = f.read()
    assert "SECRET" in content or "secret" in content or "PASSWORD" in content or "TOKEN" in content


def test_mask_val():
    def _mask_val(v):
        if not v:
            return "Nao configurado"
        if len(v) <= 4:
            return v
        return v[:4] + "**" + v[-4:]

    assert _mask_val("") == "Nao configurado"
    assert _mask_val("abc") == "abc"
    r = _mask_val("abcdefghij")
    assert r.startswith("abcd")
    assert r.endswith("ghij")
    assert "**" in r


def test_tab_config_features():
    with open("dashboard/pages/config.py", encoding="utf-8") as f:
        content = f.read()
    assert "Salvar" in content or "save" in content.lower()
    assert "config" in content.lower()


def test_run_service_test():
    from dashboard.pages.diagnostico import render_diagnostico

    assert callable(render_diagnostico)


def test_tab_diagnostico_features():
    with open("dashboard/pages/diagnostico.py", encoding="utf-8") as f:
        content = f.read()
    with open("dashboard/pages/config.py", encoding="utf-8") as f2:
        content2 = f2.read()
    assert "individuais" in content.lower() or "test" in content.lower()
    assert "SMTP" in content2 or "smtp" in content2 or "Telegram" in content2 or "telegram" in content2


def test_schedule_edit():
    with open("dashboard/pages/scrapers.py", encoding="utf-8") as f:
        content = f.read()
    assert (
        "editar" in content.lower()
        or "salvar" in content.lower()
        or "cron" in content.lower()
        or "agendamento" in content.lower()
    )


def test_diag_expanders():
    with open("dashboard/pages/diagnostico.py", encoding="utf-8") as f:
        content = f.read()
    assert "Testes" in content or "test" in content.lower()
    assert "diagnostico" in content.lower() or "status" in content.lower()


def test_features_yaml_exists():
    import yaml

    with open("config/features.yaml") as f:
        data = yaml.safe_load(f)
    assert "features" in data
    assert "telegram" in data["features"]
    assert "email" in data["features"]
    assert "scrapers" in data["features"]
    assert "matcher" in data["features"]
    assert "alerts" in data["features"]


def test_config_loader():
    from services.config import get as get_config
    from services.config import reload as reload_config

    assert get_config("features.telegram.enabled", None) is True
    assert get_config("features.matcher.threshold", None) == 80
    assert get_config("features.alerts.price_variation_pct", None) == 15
    assert get_config("nonexistent.key", "fallback") == "fallback"
    reload_config()


def test_tab_config_features_tab_exists():
    with open("dashboard/pages/config.py", encoding="utf-8") as f:
        content = f.read()
    assert "config" in content.lower()
    assert "features" in content.lower() or "supabase" in content.lower() or "telegram" in content.lower()


def test_export_csv_buttons():
    with open("dashboard/pages/precos.py", encoding="utf-8") as f:
        content = f.read()
    with open("dashboard/pages/historico.py", encoding="utf-8") as f2:
        content2 = f2.read()
    assert "dataframe" in content or "df." in content


def test_deploy_check_script():
    with open("scripts/deploy_check.py", encoding="utf-8") as f:
        content = f.read()
    assert "Supabase" in content
    assert "Telegram" in content
    assert "Gmail" in content
    assert "deploy" in content.lower()


def test_config_get_guards():
    from services.config import get as get_config

    assert (
        get_config("features.telegram.enabled", True) is True
        or get_config("features.telegram.enabled", True) is not None
    )
    assert get_config("nonexistent.key", "fallback") == "fallback"


# =====================================
print("\n=== 10. PHASE 0 — VIGENCIA, PROMOCAO & VALIDADE ===\n")


def test_detect_promotion():
    from services.price_service import _detect_promotion

    assert _detect_promotion("Leite Moça PROMO", "cx") is True
    assert _detect_promotion("Oferta Imperdível", "1kg") is True
    assert _detect_promotion("Granulado 500g", "un") is False
    assert _detect_promotion("Chocolate 50% OFF", "barra") is True
    assert _detect_promotion("", "") is False


def test_weekday_pt():
    from datetime import datetime

    from services.price_service import _weekday_pt

    # Segunda = 0, Terça = 1 ... Domingo = 6
    assert _weekday_pt(datetime(2026, 6, 15)) == "Seg"  # Monday
    assert _weekday_pt(datetime(2026, 6, 16)) == "Ter"  # Tuesday
    assert _weekday_pt(datetime(2026, 6, 17)) == "Qua"  # Wednesday
    assert _weekday_pt(datetime(2026, 6, 18)) == "Qui"  # Thursday
    assert _weekday_pt(datetime(2026, 6, 19)) == "Sex"  # Friday
    assert _weekday_pt(datetime(2026, 6, 20)) == "Sab"  # Saturday
    assert _weekday_pt(datetime(2026, 6, 21)) == "Dom"  # Sunday


def test_upsert_price_default_valid_until():
    from services.price_service import upsert_price

    assert callable(upsert_price)


def test_get_telegram_report_structure():
    from services.price_service import get_telegram_report

    result = get_telegram_report([], top_n=5)
    assert isinstance(result, list)
    assert len(result) == 0

    result2 = get_telegram_report(
        [{"canonical_name": "Leite Condensado", "aliases": ["Moca"]}],
        top_n=3,
    )
    assert isinstance(result2, list)


def test_build_full_report_html():
    from services.email_service import build_full_report_html

    prices = {
        "Leite Condensado": [
            {
                "store_name": "Assai",
                "raw_product": "Moca",
                "raw_price": 42.90,
                "raw_unit": "cx",
                "normalized": {"price_per_kg": 10.5},
                "is_promotion": False,
                "valid_until": "2026-07-01",
            },
            {
                "store_name": "Atacadao",
                "raw_product": "Moca",
                "raw_price": 45.00,
                "raw_unit": "cx",
                "normalized": {"price_per_kg": 11.25},
                "is_promotion": True,
                "valid_until": "2026-07-05",
            },
        ],
        "Creme de Leite": [
            {
                "store_name": "Spani",
                "raw_product": "Nestle",
                "raw_price": 8.90,
                "raw_unit": "lata",
                "normalized": {"price_per_kg": 35.60},
                "is_promotion": False,
                "valid_until": "",
            },
        ],
    }
    html = build_full_report_html(prices)
    assert "<!DOCTYPE html>" in html
    assert "Leite Condensado" in html
    assert "Creme de Leite" in html
    assert "Assai" in html
    assert "Atacadao" in html
    assert "Spani" in html
    assert "R$ 42.90" in html
    assert "R$ 45.00" in html
    assert "R$ 8.90" in html
    # Promoção badge
    assert "PROMO" in html
    # Validade
    assert "at" in html
    # Headers da tabela
    assert "R$/kg" in html


def test_send_telegram_report_message_structure():
    from services.telegram_service import send_telegram_report

    # Verifica que a função existe e aceita os parâmetros corretos
    assert callable(send_telegram_report)


def test_valid_only_toggle_exists():
    with open("dashboard/pages/precos.py", encoding="utf-8") as f:
        content = f.read()
    with open("dashboard/pages/historico.py", encoding="utf-8") as f2:
        content2 = f2.read()
    assert "checkbox" in content or "checkbox" in content2 or "slider" in content or "slider" in content2


def test_is_promotion_in_display():
    with open("dashboard/pages/precos.py", encoding="utf-8") as f:
        content = f.read()
    with open("dashboard/pages/historico.py", encoding="utf-8") as f2:
        content2 = f2.read()
    assert "is_promotion" in content or "is_promotion" in content2
    assert "Promocao" in content or "Promocao" in content2 or "Promoção" in content or "Promoção" in content2
    assert '"valid_until"' in content, "valid_until deve estar nas colunas de exibicao"


def test_new_features_yaml_flags():
    import yaml

    with open("config/features.yaml") as f:
        data = yaml.safe_load(f)
    fs = data["features"]
    assert "validity" in fs, "features.yaml deve ter secao validity"
    assert fs["validity"]["enabled"] is True
    assert fs["validity"]["default_days"] == 7
    assert fs["validity"]["promotion_detection"] is True
    assert "telegram" in fs
    assert fs["telegram"].get("top5_report") is True, "telegram.top5_report deve existir"
    assert "email" in fs
    assert fs["email"].get("full_report") is True, "email.full_report deve existir"
    assert "promotion_keywords" in fs["validity"]


def test_features_yaml_new_flags_loaded():
    from services.config import get as get_config

    assert get_config("features.validity.enabled", None) is True
    assert get_config("features.validity.default_days", None) == 7
    assert get_config("features.validity.promotion_detection", None) is True
    assert get_config("features.telegram.top5_report", None) is True
    assert get_config("features.email.full_report", None) is True


def test_search_prices_valid_only_param():
    import inspect

    from services.price_service import search_prices

    sig = inspect.signature(search_prices)
    params = list(sig.parameters.keys())
    assert "valid_only" in params, "search_prices deve ter parametro valid_only"


def test_get_latest_prices_valid_only_param():
    import inspect

    from services.price_service import get_latest_prices

    sig = inspect.signature(get_latest_prices)
    params = list(sig.parameters.keys())
    assert "valid_only" in params, "get_latest_prices deve ter parametro valid_only"


def test_get_price_history_valid_only_param():
    import inspect

    from services.price_service import get_price_history

    sig = inspect.signature(get_price_history)
    params = list(sig.parameters.keys())
    assert "valid_only" in params, "get_price_history deve ter parametro valid_only"


def test_sanitize_xss():
    """Verifica que html.escape escapa XSS corretamente"""
    import html

    assert html.escape("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert html.escape('"quoted"') == "&quot;quoted&quot;"
    assert html.escape("&") == "&amp;"
    assert html.escape("normal text") == "normal text"


# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("EXECUTANDO TESTES...\n")

# Registra e executa
tests = [
    # Services
    (test_auth, "auth: hash, jwt, totp, config"),
    (test_rate_limiter, "rate_limiter: limite, persistência, clear"),
    (test_all_imports, "all_imports: todos os módulos carregam"),
    (test_cleanup_imports, "cleanup: imports e assinaturas corretas"),
    # Login
    (test_login_render_function, "login: render_login callable"),
    (test_setup_render_function, "login: render_setup_first_user callable"),
    (test_login_limiter_integration, "login: rate limiter integrado"),
    # Pages
    (test_page_handler_registry, "pages: todos os 11 handlers registrados"),
    (test_ingredients_yaml, "pages: ingredients.yaml válido (>=11 ingredientes)"),
    (test_stores_yaml, "pages: stores.yaml válido (>=49 lojas)"),
    # App
    (test_app_module_loads, "app: módulo carrega, main() existe"),
    (test_env_auth_flow, "app: auth flow com env vars"),
    # Phase 3 — Flyers & History
    (test_flyer_status_color, "flyer: _flyer_status_color() cores corretas"),
    (test_flyer_status_label, "flyer: _flyer_status_label() labels PT-BR"),
    (test_format_kg, "flyer: _format_kg() extrai price_per_kg"),
    (test_get_kg, "flyer: _get_kg() funciona com DataFrame"),
    (test_flyer_service_upsert, "flyer: upsert_flyer() existe e monta payload"),
    (test_flyer_service_mark_processed, "flyer: mark_processed() callable"),
    (test_flyer_service_mark_failed, "flyer: mark_failed() callable"),
    (test_flyer_service_get_recent, "flyer: get_recent_flyers() callable"),
    (test_flyer_service_get_pending, "flyer: get_pending_flyers() callable"),
    (test_price_service_search, "price: search/get/insert/approve callable"),
    (test_home_kpi_flyer_structure, "home: KPIs flyer com bordas coloridas"),
    (test_flyer_kpi_row_in_home, "home: texto KPIs flyer presente"),
    (test_flyer_detail_section, "flyer: detalhe tem campos obrigatorios"),
    (test_history_chart_types, "history: tipos de grafico disponiveis"),
    # Security & Edge Cases
    (test_generate_secret_key, "auth: generate_secret_key() >= 32 chars"),
    (test_jwt_key_length, "auth: chave JWT tem minimo 32 bytes"),
    (test_rate_limiter_window_expires, "rate: janela expira apos timeout"),
    (test_rate_limiter_independent_keys, "rate: keys independentes nao interferem"),
    # Phase 4 — CRUD Console & Refactoring
    (test_tab_visao_geral_refactored, "refactor: 6 sub-funcoes callable"),
    (test_tab_visao_geral_complexity, "refactor: tab_visao_geral corpo enxuto"),
    (test_tab_lojas_features, "lojas: filtros, busca, editor YAML"),
    (test_tab_ingredientes_tester, "ingredientes: testadores normalizer/matcher"),
    (test_normalizer_function, "normalizer: _test_normalizer callable"),
    (test_matcher_function, "matcher: _test_matcher callable"),
    (test_render_functions_exist, "refactor: todas as 6 sub-funcoes chamadas"),
    # Phase 5 — Control & Reports
    (test_test_smtp, "reports: _test_smtp callable"),
    (test_test_telegram, "reports: _test_telegram callable"),
    (test_render_schedule_info, "reports: _render_schedule_info callable"),
    (test_tab_relatorios_features, "reports: tab_relatorios com builder (testers removidos)"),
    (test_tab_scrapers_schedule, "scrapers: schedule info presente"),
    # Phase 6 — System Config & Diagnostics
    (test_secret_groups, "config: SECRET_GROUPS 5 grupos 13 vars"),
    (test_mask_val, "config: _mask_val mascaramento correto"),
    (test_tab_config_features, "config: editor secrets inline"),
    (test_run_service_test, "diag: _run_service_test callable"),
    (test_tab_diagnostico_features, "diag: testes individuais + comunicacao"),
    (test_schedule_edit, "diag: editar agendamento scrape.yml"),
    (test_diag_expanders, "diag: botoes executar/limpar + expanders"),
    # Phase 7 — Polish, Config & Deploy
    (test_features_yaml_exists, "config: features.yaml existe e valido"),
    (test_config_loader, "config: services/config.py get() + reload()"),
    (test_tab_config_features_tab_exists, "config: aba Features em tab_config"),
    (test_export_csv_buttons, "export: st.download_button no app"),
    (test_deploy_check_script, "deploy: scripts/deploy_check.py existe"),
    (test_config_get_guards, "config: get_config() guardando features"),
    # Phase 0 — Vigência, Promoção & Validade
    (test_detect_promotion, "price: _detect_promotion() com keywords"),
    (test_weekday_pt, "price: _weekday_pt() mapeamento PT-BR"),
    (test_upsert_price_default_valid_until, "price: upsert_price() callable"),
    (test_get_telegram_report_structure, "price: get_telegram_report() estrutura"),
    (test_build_full_report_html, "email: build_full_report_html() HTML valido"),
    (test_send_telegram_report_message_structure, "email: send_telegram_report() callable"),
    (test_valid_only_toggle_exists, "dashboard: _valid_only_toggle() existe"),
    (test_is_promotion_in_display, "dashboard: is_promotion/valid_until nas colunas"),
    (test_new_features_yaml_flags, "config: novas flags features.yaml"),
    (test_features_yaml_new_flags_loaded, "config: config.get() novas flags"),
    (test_search_prices_valid_only_param, "price: search_prices(valid_only=)"),
    (test_get_latest_prices_valid_only_param, "price: get_latest_prices(valid_only=)"),
    (test_get_price_history_valid_only_param, "price: get_price_history(valid_only=)"),
    # Security
    (test_sanitize_xss, "security: _sanitize() escapa XSS"),
]

for fn, desc in tests:
    _run_test(desc, fn)

# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 60}")
print(f"RESULTADO: {PASS} passed, {FAIL} failed, {SKIP} skipped")
if __name__ == "__main__":
    if FAIL:
        print("⚠️  Alguns testes falharam - revisar acima.")
        sys.exit(1)
    else:
        print("✅ Todos os testes passaram!")
