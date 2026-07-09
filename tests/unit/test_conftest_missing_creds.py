"""
Regression tests for tests/conftest.py helper _has_real_db().

Garante que a funcao NAO exige SUPABASE_DB_PASSWORD (legado psycopg2/5432).
Conforme AGENTS.md regra #3, o projeto usa SOMENTE exec_sql_query RPC porta 443,
entao basta SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (ou ANON_KEY).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFTEST_PATH = REPO_ROOT / "tests" / "conftest.py"


def _load_conftest_with_env(env_dict: dict[str, str]):
    """Carrega tests/conftest.py em modulo isolado com env controlado.

    O conftest original chama load_dotenv() no import, mas se a cwd NAO tiver
    .env, ele nao carrega nada e respeita os.environ pre-existente.
    Aqui usamos uma cwd temporaria (tmp_path) e importamos o modulo em outro
    nome ("conftest_under_test") para nao conflitar com importacoes reais.
    """
    saved_env = os.environ.copy()
    saved_cwd = os.getcwd()
    try:
        os.environ.clear()
        os.environ.update(env_dict)
        if hasattr(sys, "_called_from_test"):
            os.chdir(str(REPO_ROOT.parent))  # cwd sem .env
        spec = importlib.util.spec_from_file_location(
            "conftest_under_test", CONFTEST_PATH
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        os.chdir(saved_cwd)
        os.environ.clear()
        os.environ.update(saved_env)


@pytest.fixture
def env_loader(monkeypatch, tmp_path, request):
    """Devolve funcao que recebe dict e retorna o modulo com esse env."""
    monkeypatch.chdir(tmp_path)
    # Evita que o dotenv ache o .env do projeto
    if hasattr(sys, "_called_from_test"):
        monkeypatch.chdir(request.config.rootdir.parent)
    return _load_conftest_with_env


def test_has_real_db_false_quando_env_vazio(env_loader):
    """Sem nenhuma credencial: deve retornar False."""
    module = env_loader(
        {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        }
    )
    assert module._has_real_db() is False


def test_has_real_db_true_com_url_e_service_role_sem_db_password(env_loader):
    """Cenario CRITICO (cobre a regressao original):

    URL + SUPABASE_SERVICE_ROLE_KEY, SEM SUPABASE_DB_PASSWORD, deve
    retornar True. Este era o caso em que TODOS os 112 testes de integration
    eram pulados em CI.
    """
    module = env_loader(
        {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "SUPABASE_URL": "https://abcdefghijk.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "eyJ-test.service-role-key-value",
        }
    )
    assert module._has_real_db() is True


def test_has_real_db_true_com_anon_key_como_fallback(env_loader):
    """Fallback para SUPABASE_ANON_KEY tambem deve funcionar."""
    module = env_loader(
        {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "SUPABASE_URL": "https://abcdefghijk.supabase.co",
            "SUPABASE_ANON_KEY": "eyJ-test-anon-key-value",
        }
    )
    assert module._has_real_db() is True


def test_has_real_db_false_apenas_com_legacy_db_password(env_loader):
    """SUPABASE_DB_PASSWORD sozinho NAO deve ativar (legado psycopg2)."""
    module = env_loader(
        {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "SUPABASE_URL": "https://abcdefghijk.supabase.co",
            "SUPABASE_DB_PASSWORD": "qualquer-senha-legada",
        }
    )
    assert module._has_real_db() is False


def test_has_real_db_false_com_project_ref_muito_curto(env_loader):
    """URL com project ref < 10 chars deve retornar False (sanity check)."""
    module = env_loader(
        {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "SUPABASE_URL": "https://abc.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "eyJ-test",
        }
    )
    assert module._has_real_db() is False
