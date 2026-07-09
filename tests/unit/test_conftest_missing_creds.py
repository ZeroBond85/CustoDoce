"""Cobre o bug em tests/conftest.py:_has_real_db().

Ate 2026-07-09, _has_real_db() exigia SUPABASE_DB_PASSWORD (legado psycopg2/5432),
mas AGENTS.md regra #3 proibe psycopg2. CI jobs sem DB_PASSWORD skipavam 112 testes.
Correcao: agora exige SUPABASE_URL + (SERVICE_ROLE_KEY OU ANON_KEY).
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest


CONFTEST_PATH = Path(__file__).resolve().parent.parent.parent / "tests" / "conftest.py"


def _reload_conftest(env_overrides: dict[str, str] | None = None) -> ModuleType:
    """Recarrega conftest em cwd isolado + com env controlado.

    Bloqueia load_dotenv() para evitar que .env real contamine o teste.
    """
    # Limpa modulos do conftest
    for name in list(sys.modules):
        if name == "tests.conftest" or name.startswith("tests.conftest."):
            sys.modules.pop(name, None)
    # Aplica env limpo primeiro
    for k in (
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "SUPABASE_DB_PASSWORD",
        "GROQ_API_KEY",
    ):
        os.environ.pop(k, None)
    # Aplica overrides
    if env_overrides:
        for k, v in env_overrides.items():
            os.environ[k] = v
    # Bloqueia load_dotenv no modulo carregado
    with patch("dotenv.load_dotenv", lambda *a, **kw: None):
        spec = importlib.util.spec_from_file_location(
            "cf_under_test_for_test", CONFTEST_PATH
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


@pytest.fixture
def cf_no_dotenv(monkeypatch, tmp_path):
    """Carrega conftest sem .env (cwd em tmp vazio) + env limpo."""
    monkeypatch.chdir(tmp_path)
    return _reload_conftest()


def test_has_real_db_false_quando_env_minimo(cf_no_dotenv):
    """Sem URL nem key: retorna False."""
    assert cf_no_dotenv._has_real_db() is False


def test_has_real_db_true_com_url_e_service_role_sem_db_password(monkeypatch, tmp_path):
    """Cenario CRITICO (cobre regressao original).

    URL + SUPABASE_SERVICE_ROLE_KEY, sem DB_PASSWORD, retorna True.
    Era o caso que estava auto-skipando todos os 112 testes em CI.
    """
    monkeypatch.chdir(tmp_path)
    module = _reload_conftest(
        {
            "SUPABASE_URL": "https://abcdefghijk.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "eyJ-test.service-role-key-value",
        }
    )
    assert module._has_real_db() is True


def test_has_real_db_true_com_anon_key_como_fallback(monkeypatch, tmp_path):
    """Fallback para SUPABASE_ANON_KEY tambem funciona."""
    monkeypatch.chdir(tmp_path)
    module = _reload_conftest(
        {
            "SUPABASE_URL": "https://abcdefghijk.supabase.co",
            "SUPABASE_ANON_KEY": "eyJ-test-anon-key-value",
        }
    )
    assert module._has_real_db() is True


def test_has_real_db_false_apenas_com_legacy_db_password(monkeypatch, tmp_path):
    """SUPABASE_DB_PASSWORD sozinho NAO ativa (legado psycopg2)."""
    monkeypatch.chdir(tmp_path)
    module = _reload_conftest(
        {
            "SUPABASE_URL": "https://abcdefghijk.supabase.co",
            "SUPABASE_DB_PASSWORD": "qualquer-senha-legada",
        }
    )
    assert module._has_real_db() is False


def test_has_real_db_false_com_project_ref_muito_curto(monkeypatch, tmp_path):
    """URL com project ref < 10 chars retorna False (sanity)."""
    monkeypatch.chdir(tmp_path)
    module = _reload_conftest(
        {
            "SUPABASE_URL": "https://abc.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "eyJ-test",
        }
    )
    assert module._has_real_db() is False
