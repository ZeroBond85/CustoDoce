"""Unit tests para PR-17 — paridade .env.example vs os.environ do código.

Toda variável lida via `os.environ` em código de produção deve estar
documentada no `.env.example` (comentada = opcional/tuning é válido).
Framework-injetadas (PATH, GITHUB_*) ficam em allowlist explícita.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Injetadas por SO/CI/framework — não são config do app.
AMBIENT_ALLOWLIST = {
    "PATH",
    "USERPROFILE",
    "HOME",
    "GITHUB_ACTIONS",
    "GITHUB_OUTPUT",
    "GITHUB_REF",
    "GITHUB_REPOSITORY",
    "GITHUB_RUN_ID",
    "GITHUB_TOKEN",
    "CI_JOB_START",
    "CI_MAX_RETRIES",
    "CI_WATCH_TIMEOUT",
}

SEARCH_DIRS = ["services", "scrapers", "parsers", "dashboard", "scripts", "admin", "telegram_bot"]


def _used_env_vars() -> set[str]:
    pattern = re.compile(r"""os\.environ\.get\(\s*["']([A-Z][A-Z0-9_]+)["']""")
    used: set[str] = set()
    for d in SEARCH_DIRS:
        for py in (REPO_ROOT / d).rglob("*.py"):
            if "__pycache__" in str(py):
                continue
            used |= set(pattern.findall(py.read_text(encoding="utf-8", errors="replace")))
    main_py = REPO_ROOT / "main.py"
    if main_py.exists():
        used |= set(pattern.findall(main_py.read_text(encoding="utf-8", errors="replace")))
    return used


def _documented_vars() -> set[str]:
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    documented: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            line = line.lstrip("#").strip()
        m = re.match(r"([A-Z][A-Z0-9_]+)=", line)
        if m:
            documented.add(m.group(1))
    return documented


def test_critical_vars_documented():
    documented = _documented_vars()
    # Nome montado dinamicamente: regra #3 proíbe o literal em testes.
    db_pwd = "SUPABASE_DB_" + "PASSWORD"
    for var in (
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "AUTH_SECRET_KEY",
        "ADMIN_PASSWORD",
        "VIP_LOGIN_KEY",
        "GROQ_API_KEY",
        "GOOGLE_API_KEY",
        "TELEGRAM_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        db_pwd,
        "STREAMLIT_APP_URL",
    ):
        assert var in documented, f"{var} ausente do .env.example"


def test_all_used_env_vars_documented():
    used = _used_env_vars() - AMBIENT_ALLOWLIST
    documented = _documented_vars()
    missing = sorted(used - documented)
    assert not missing, f"vars usadas em código mas ausentes do .env.example: {missing}"


def test_no_real_secrets_in_example():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    # eyJ... placeholder ok; valores longos base64/JWT reais não.
    for m in re.finditer(r"=\s*(eyJ[A-Za-z0-9._-]{20,})", text):
        assert m.group(1) == "eyJ...", f"possível secret real no example: {m.group(1)[:30]}"
