# tests/conftest.py
"""
Fixtures centralizadas — todas as suítes importam daqui.
Uso:
    pytest tests/unit/           # mocks
    pytest tests/integration/    # DB real (auto-skip sem creds)
    pytest tests/e2e/            # Playwright
    pytest tests/real/           # scrapers reais
    pytest tests/schema/         # validação schema DB via RPC
"""

import os
import sys
import importlib
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv

# Carrega .env ANTES de qualquer import para garantir que credenciais estejam disponíveis
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Garante que a raiz do projeto esteja no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Helpers ─────────────────────────────────────────────────────
def _has_real_db() -> bool:
    """Verifica se credenciais Supabase reais estão configuradas."""
    url = os.environ.get("SUPABASE_URL", "")
    pwd = os.environ.get("SUPABASE_DB_PASSWORD", "")
    if not url or not pwd:
        return False
    try:
        proj = url.split("//")[1].split(".")[0]
        return len(proj) > 10
    except Exception:
        return False


def _has_groq_key() -> bool:
    """Verifica se GROQ_API_KEY está configurado."""
    key = os.environ.get("GROQ_API_KEY", "")
    return bool(key and key.startswith("gsk_"))


def _has_playwright() -> bool:
    """Verifica se playwright está instalado (simplificado)."""
    return True


# ── Fixtures Mock (Unit Tests) ──────────────────────────────────
@pytest.fixture
def mock_supabase():
    """Cliente Supabase 100% mockado para testes unitários."""
    from tests.test_services_mocked import make_mocks

    mock_client, table, qb = make_mocks()
    return mock_client


@pytest.fixture
def mock_config_db():
    """config_db mockado com dados de teste determinísticos."""
    mock = MagicMock()
    mock.get_all_ingredients.return_value = [
        {
            "id": "ing-1",
            "canonical_name": "Leite Condensado",
            "aliases": ["Leite Condensado Moça", "Leite Cond Molico"],
            "search_terms": ["leite condensado"],
            "brands": ["Moça", "Molico"],
            "exclude_terms": [],
            "active": True,
        },
        {
            "id": "ing-2",
            "canonical_name": "Creme de Leite",
            "aliases": ["Creme de Leite Nestlé"],
            "search_terms": ["creme de leite"],
            "brands": ["Nestlé"],
            "exclude_terms": [],
            "active": True,
        },
    ]
    mock.get_all_stores.return_value = [
        {"id": "assai", "name": "Assaí", "tier": 1, "type": "flyer", "city": "Santos", "is_active": True},
        {
            "id": "rizzoshop",
            "name": "RizzoShop",
            "tier": 2,
            "type": "website_catalog",
            "city": "São Paulo",
            "is_active": True,
        },
    ]
    mock.get_scrape_frequency.return_value = {"frequency_minutes": 60, "enabled": True}
    mock.get_active_recipients.return_value = []
    mock.get_all_alert_rules.return_value = []
    mock.get_feature_flag.return_value = True
    mock.get_all_feature_flags.return_value = {}
    return mock


# ── Fixtures Real DB (via REST API RPC exec_sql_query) ──────────
class _SchemaCursor:
    """Mimetiza psycopg2 cursor usando exec_sql_query RPC (porta 443)."""

    def __init__(self, client):
        self.client = client
        self._rows = []
        self._index = 0

    def execute(self, sql, params=None):
        sql = sql.rstrip("; \t\n")
        if params:
            if isinstance(params, tuple):
                for p in params:
                    if isinstance(p, str):
                        sql = sql.replace("%s", f"'{p.replace(chr(39), chr(39) + chr(39))}'", 1)
                    else:
                        sql = sql.replace("%s", str(p), 1)
            elif isinstance(params, dict):
                for k, v in params.items():
                    ph = f"%({k})s"
                    if isinstance(v, str):
                        sql = sql.replace(ph, f"'{v.replace(chr(39), chr(39) + chr(39))}'")
                    else:
                        sql = sql.replace(ph, str(v))

        # Chamada via REST API (porta 443)
        r = self.client.rpc("exec_sql_query", {"sql": sql}).execute()

        # Convert list of dicts to list of tuples to mimic psycopg2
        if isinstance(r.data, list) and len(r.data) > 0:
            keys = r.data[0].keys()
            self._rows = [tuple(row.values()) for row in r.data]
        else:
            self._rows = []

        self._index = 0

    def fetchone(self):
        if self._index < len(self._rows):
            row = self._rows[self._index]
            self._index += 1
            return row
        return None

    def fetchall(self):
        return self._rows[self._index :]

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _SchemaConn:
    def cursor(self):
        return _SchemaCursor(self._client)


@pytest.fixture
def db_conn():
    """
    Conexão ao Supabase via exec_sql_query RPC (porta 443).
    Lida com a poluição de cache de módulos causada por MagicMocks nos testes unitários.
    """
    import importlib
    import importlib.util

    # Força recarga do supabase_client do disco para limpar mocks de sys.modules
    real_path = Path(__file__).parent.parent / "services" / "supabase_client.py"
    spec = importlib.util.spec_from_file_location("services.supabase_client", str(real_path))
    supabase_client = importlib.util.module_from_spec(spec)
    sys.modules["services.supabase_client"] = supabase_client
    spec.loader.exec_module(supabase_client)

    supabase_client._supabase_client = None
    supabase_client._service_client = None

    conn = _SchemaConn()
    conn._client = supabase_client.get_service_client()
    yield conn


@pytest.fixture(scope="session")
def real_supabase():
    """Cliente Supabase service role REAL — recarrega módulo limpo."""
    if not _has_real_db():
        pytest.skip("SUPABASE_SERVICE_ROLE_KEY não configurado")

    # Limpa cache de módulos services/ para evitar conflitos com mocks
    for mod in list(sys.modules):
        if mod.startswith("services."):
            sys.modules.pop(mod, None)

    real_path = Path(__file__).parent.parent / "services" / "supabase_client.py"
    spec = importlib.util.spec_from_file_location("services.supabase_client", str(real_path))
    sc = importlib.util.module_from_spec(spec)
    sys.modules["services.supabase_client"] = sc
    spec.loader.exec_module(sc)

    sc._supabase_client = None
    sc._service_client = None
    return sc.get_service_client()


@pytest.fixture(scope="session")
def supabase_client(real_supabase):
    """Alias semantico de real_supabase — para tests que esperam este nome."""
    return real_supabase


# ── Auto-skip markers ──────────────────────────────────────────
def pytest_configure(config):
    # Registra markers para evitar warnings do pytest
    config.addinivalue_line("markers", "unit: testes puros (mock, zero rede/DB)")
    config.addinivalue_line("markers", "integration: testes com DB real (precisa .env)")
    config.addinivalue_line("markers", "e2e: Playwright + Streamlit real")
    config.addinivalue_line("markers", "real: scrapers reais (lento, flaky)")
    config.addinivalue_line("markers", "schema: validação schema DB via RPC")
    config.addinivalue_line("markers", "performance: benchmarks <200ms")
    config.addinivalue_line("markers", "llm: precisa GROQ_API_KEY")


def pytest_collection_modifyitems(items):
    """Pula testes automaticamente se as credenciais necessárias estiverem ausentes."""
    for item in items:
        if (
            "integration" in item.keywords or "real" in item.keywords or "schema" in item.keywords
        ) and not _has_real_db():
            item.add_marker(pytest.mark.skip(reason="SUPABASE_URL ou SUPABASE_DB_PASSWORD não configurados"))

        if "llm" in item.keywords and not _has_groq_key():
            item.add_marker(pytest.mark.skip(reason="GROQ_API_KEY não configurado"))

        if "e2e" in item.keywords and not _has_playwright():
            item.add_marker(pytest.mark.skip(reason="Playwright não configurado"))


# ── Session cleanup ─────────────────────────────────────────────
@pytest.fixture(autouse=True, scope="session")
def _cleanup_test_data():
    """Limpa dados de teste (_test_*) ao final da session se DB real."""
    yield
    if _has_real_db():
        try:
            from services.supabase_client import get_service_client

            client = get_service_client()
            cleanups = [
                "prices",
                "price_history",
                "review_queue",
                "scraping_logs",
                "flyers",
            ]
            for table in cleanups:
                try:
                    sql = f"DELETE FROM {table} WHERE store_name LIKE '_test_%' OR raw_product LIKE '_test_%' OR ingredient_id LIKE '_test_%'"  # noqa: S608
                    client.rpc("exec_sql_query", {"sql": sql}).execute()
                except Exception:
                    pass
        except Exception:
            pass  # fallback gracioso se RPC falhar
