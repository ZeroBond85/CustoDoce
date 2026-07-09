"""Cobre o bug em tests/conftest.py:_has_real_db().

Ate 2026-07-09, _has_real_db() exigia SUPABASE_DB_PASSWORD (legado psycopg2/5432),
mas AGENTS.md regra #3 proibe psycopg2. CI jobs sem DB_PASSWORD skipavam 112 testes.
Correcao: agora exige SUPABASE_URL + (SERVICE_ROLE_KEY OU ANON_KEY).
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest


CONFTEST_PATH = Path(__file__).resolve().parent.parent.parent / "tests" / "conftest.py"


@pytest.fixture
def cf_no_dotenv(monkeypatch, tmp_path):
    """Carrega tests.conftest.py SEM poluicao do .env no import.

    O conftest.py chama ``load_dotenv(Path(__file__).resolve().parent.parent / ".env")``
    incondicionalmente no import. Para garantir isolamento, monkeypatchmos
    ``dotenv.load_dotenv`` para no-op ANTES do ``exec_module``. Sem isso, o
    .env do projeto (se existir) eh injetado no ``os.environ`` DENTRO do modulo,
    contaminando o teste mesmo apos ``monkeypatch.delenv``.
    """
    import dotenv

    monkeypatch.chdir(tmp_path)
    for k in (
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "SUPABASE_DB_PASSWORD",
        "GROQ_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    for name in list(sys.modules):
        if name.startswith("tests.conftest") or name == "tests.conftest":
            sys.modules.pop(name, None)
    # No-op para isolar o modulo de qualquer .env local durante o import.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    spec = importlib.util.spec_from_file_location("cf_no_dotenv_for_test", CONFTEST_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_has_real_db_false_quando_env_minimo(cf_no_dotenv):
    """Sem URL nem key: retorna False."""
    assert cf_no_dotenv._has_real_db() is False


def test_has_real_db_true_com_url_e_service_role_sem_db_password(cf_no_dotenv, monkeypatch, tmp_path):
    """Cenario CRITICO (cobre regressao original).

    URL + SUPABASE_SERVICE_ROLE_KEY, sem DB_PASSWORD, retorna True.
    Era o caso que estava auto-skipando todos os 112 testes em CI.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SUPABASE_URL", "https://abcdefghijk.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "eyJ-test.service-role-key-value")
    monkeypatch.delenv("SUPABASE_DB_PASSWORD", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    assert cf_no_dotenv._has_real_db() is True


def test_has_real_db_true_com_anon_key_como_fallback(cf_no_dotenv, monkeypatch, tmp_path):
    """Fallback para SUPABASE_ANON_KEY tambem funciona."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SUPABASE_URL", "https://abcdefghijk.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "eyJ-test-anon-key-value")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_DB_PASSWORD", raising=False)
    assert cf_no_dotenv._has_real_db() is True


def test_has_real_db_false_apenas_com_legacy_db_password(cf_no_dotenv, monkeypatch, tmp_path):
    """SUPABASE_DB_PASSWORD sozinho NAO ativa (legado psycopg2)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SUPABASE_URL", "https://abcdefghijk.supabase.co")
    monkeypatch.setenv("SUPABASE_DB_PASSWORD", "qualquer-senha-legada")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    assert cf_no_dotenv._has_real_db() is False


def test_has_real_db_false_com_project_ref_muito_curto(cf_no_dotenv, monkeypatch, tmp_path):
    """URL com project ref < 10 chars retorna False (sanity)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "eyJ-test")
    assert cf_no_dotenv._has_real_db() is False
