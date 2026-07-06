"""
Testes unitários para parsers/llm_cache.py (Fase 4.8 - Recurso 3).

Cobre:
- Cache hit/miss
- TTL expiry
- Persistência SQLite em memória
- Hash de chave consistente
- Cleanup de TTL
- Stats
"""

from datetime import datetime, timedelta

import pytest


@pytest.fixture
def isolated_cache(monkeypatch, tmp_path):
    """Isola o cache para `:memory:` SQLite (evita problema de file-lock do Windows)."""
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_CACHE_TTL_DAYS", "30")
    monkeypatch.setenv("LLM_CACHE_DB_PATH", ":memory:")  # Opcional

    import importlib

    import parsers.llm_cache as lc

    importlib.reload(lc)

    # Forçar todas conexões para :memory:
    monkeypatch.setattr(lc, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(lc, "_CACHE_DB", tmp_path / "llm_cache.db")
    # Usar arquivo real em tmp_path (Windows tolera remover após close)

    yield lc

    # Cleanup explícito
    try:
        db_file = tmp_path / "llm_cache.db"
        if db_file.exists():
            db_file.unlink()
    except Exception:
        pass


def test_cache_miss_returns_none(isolated_cache):
    lc = isolated_cache
    result = lc.get_cache("Product Not In Cache")
    assert result is None


def test_cache_set_and_get(isolated_cache):
    lc = isolated_cache
    decision = {
        "match": True,
        "canonical_name": "Leite Condensado",
        "confidence_score": 0.92,
        "reason": "Direct match",
        "provider": "groq",
    }
    lc.set_cache("Leite Condensado Moça 395g", "Moça", decision)
    got = lc.get_cache("Leite Condensado Moça 395g", "Moça")
    assert got == decision


def test_cache_key_lowercase_and_trim():
    """Hash key deve ser case-insensitive."""
    from parsers.llm_cache import _hash_key

    a = _hash_key("PRODUCT A", "B")
    b = _hash_key("product a", "b")
    assert a == b


def test_cache_brand_distinguished(isolated_cache):
    lc = isolated_cache
    decision_a = {"match": True, "ingredient": "A"}
    decision_b = {"match": True, "ingredient": "B"}
    lc.set_cache("SameProduct", "BrandA", decision_a)
    lc.set_cache("SameProduct", "BrandB", decision_b)
    assert lc.get_cache("SameProduct", "BrandA") == decision_a
    assert lc.get_cache("SameProduct", "BrandB") == decision_b


def test_cache_miss_empty_product(isolated_cache):
    lc = isolated_cache
    assert lc.get_cache("") is None
    assert lc.get_cache(None) is None


def test_ttl_expiry(isolated_cache):
    """Decisão antiga > TTL retorna None."""
    lc = isolated_cache
    decision = {"match": True, "ingredient": "X"}
    # 1 dia TTL
    lc.set_cache("WillExpire", "", decision, ttl_days=1)
    # Backdate o row
    long_ago = (datetime.now() - timedelta(days=40)).isoformat()
    with lc._get_conn() as conn:
        conn.execute(
            "UPDATE cache SET created_at = ? WHERE product_name = ?",
            (long_ago, "WillExpire"),
        )
        conn.commit()
    # Now it should be expired
    assert lc.get_cache("WillExpire") is None


def test_cleanup_ttl_removes_old(isolated_cache):
    lc = isolated_cache
    lc.set_cache("OldEntry", "", {"match": True}, ttl_days=10)
    long_ago = (datetime.now() - timedelta(days=40)).isoformat()
    with lc._get_conn() as conn:
        conn.execute(
            "UPDATE cache SET created_at = ? WHERE product_name = ?",
            (long_ago, "OldEntry"),
        )
        conn.commit()
    removed = lc.cleanup_ttl(ttl_days=30)
    assert removed >= 1
    assert lc.get_cache("OldEntry") is None


def test_init_schema_idempotent(isolated_cache):
    lc = isolated_cache
    lc._init_schema()
    lc._init_schema()
    lc._init_schema()
    # If we got here, it's idempotent
    assert True


def test_cache_stats(isolated_cache):
    lc = isolated_cache
    lc.set_cache("item1", "", {"x": 1})
    lc.set_cache("item2", "", {"x": 2})
    stats = lc.cache_stats()
    assert stats["total"] == 2
    assert stats["ttl_days"] == 30


def test_cache_unicode_keys(isolated_cache):
    """Aceita caracteres acentuados."""
    lc = isolated_cache
    decision = {"match": True, "ingredient": "Açúcar"}
    lc.set_cache("Açúcar Cristal", "", decision)
    assert lc.get_cache("Açúcar Cristal") == decision


def test_set_cache_overwrites(isolated_cache):
    """Set com mesma chave sobrescreve."""
    lc = isolated_cache
    lc.set_cache("p", "", {"v": 1})
    lc.set_cache("p", "", {"v": 2})
    assert lc.get_cache("p") == {"v": 2}
