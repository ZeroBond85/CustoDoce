#!/usr/bin/env python3
"""CustoDoce — Deploy Health Check
Roda antes do deploy para validar: Supabase, Gmail, Telegram, config.
Uso: python scripts/deploy_check.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Carrega .env se existir (para ambiente local)
_dotenv = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_dotenv):
    with open(_dotenv) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and "=" in _line and not _line.startswith("#"):
                _k, _v = _line.split("=", 1)
                _v = _v.strip("\"'")
                os.environ.setdefault(_k.strip(), _v)

PASS = 0
FAIL = 0


def _check(label: str, fn):
    global PASS, FAIL
    start = time.time()
    try:
        fn()
        elapsed = time.time() - start
        print(f"  [OK] {label} ({elapsed:.2f}s)")
        PASS += 1
    except Exception as e:
        elapsed = time.time() - start
        print(f"  [FAIL] {label} — {e} ({elapsed:.2f}s)")
        FAIL += 1


def test_supabase():
    from services.supabase_client import get_supabase as gs
    client = gs()
    resp = client.table("prices").select("count", count="exact").limit(1).execute()
    assert resp.count is not None, "Supabase nao retornou count"


def test_yaml_configs():
    import yaml
    for path in ["config/ingredients.yaml", "config/stores.yaml", "config/features.yaml"]:
        with open(path, encoding="utf-8") as f:
            yaml.safe_load(f)


def test_features_config():
    from services.config import get as get_config
    assert get_config("features.telegram.enabled", None) is not None
    assert get_config("features.email.enabled", None) is not None
    assert get_config("features.alerts.price_variation_pct", None) is not None


def test_auth():
    from services.auth import hash_password, verify_password
    h = hash_password("deploy_test")
    assert verify_password("deploy_test", h), "Auth hash/verify falhou"


def test_rate_limiter():
    from services.rate_limiter import RateLimiter
    rl = RateLimiter()
    assert rl.is_limited("deploy_test_key") is False


def test_telegram():
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise ValueError("TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID nao configurados")
    import httpx
    resp = httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": "🚀 CustoDoce — Deploy check OK"},
        timeout=15,
    )
    assert resp.status_code == 200, f"Telegram erro: {resp.status_code}"


def test_smtp():
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or "587")
    user = os.environ.get("SMTP_USER") or os.environ.get("GMAIL_USER")
    password = os.environ.get("SMTP_PASSWORD") or os.environ.get("GMAIL_APP_PASSWORD")
    from_addr = os.environ.get("SMTP_FROM") or user
    email_to = os.environ.get("ALERT_EMAIL_TO")
    if not user or not password or not email_to:
        raise ValueError("SMTP_USER/GMAIL_USER, SMTP_PASSWORD/GMAIL_APP_PASSWORD ou ALERT_EMAIL_TO nao configurados")
    import smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg.set_content("🚀 CustoDoce — Deploy check OK")
    msg["Subject"] = "CustoDoce - Deploy Check"
    msg["From"] = f"CustoDoce <{from_addr}>"
    msg["To"] = email_to
    with smtplib.SMTP(host, port, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.login(user, password)
        server.send_message(msg)


if __name__ == "__main__":
    print("=" * 55)
    print("  CustoDoce — Deploy Health Check")
    print("=" * 55)

    _check("Supabase conexao", test_supabase)
    _check("YAML configs (3 arquivos)", test_yaml_configs)
    _check("Features config (services/config.py)", test_features_config)
    _check("Auth (hash + verify)", test_auth)
    _check("Rate Limiter", test_rate_limiter)
    env_checks = ["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY",
                   "AUTH_SECRET_KEY", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD",
                   "GMAIL_USER", "GMAIL_APP_PASSWORD",
                   "ALERT_EMAIL_TO"]
    def _check_env(v):
        val = os.environ.get(v)
        if not val:
            raise ValueError(f"{v} nao configurado")
        return val

    for var in env_checks:
        _check(f"ENV: {var}", lambda v=var: _check_env(v))
    _check("Telegram envio", test_telegram)
    _check("SMTP envio", test_smtp)

    print(f"\n{'=' * 55}")
    print(f"  Resultado: {PASS} passed, {FAIL} failed")
    if FAIL:
        print("  [!] Corrigir antes do deploy.")
        sys.exit(1)
    else:
        print("  [OK] Pronto para deploy!")
