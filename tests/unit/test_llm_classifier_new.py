"""
Testes unitários para parsers/llm_classifier.py (REFATORADO - Fase 4.8)
"""

from unittest.mock import patch

import pytest


@pytest.fixture
def mock_strategies():
    """Retorna [failure, success] strategies."""
    from parsers.llm_strategies import LLMResult

    class FakeSuccess:
        provider_name = "fake_success"

        def classify(self, product_text, candidates):
            return LLMResult(
                match=True,
                canonical_name="fake_can",
                confidence_score=0.95,
                reason="test reason",
                provider="fake_success",
            )

    class FakeFailure:
        provider_name = "fake_failure"
        failure_count = 0

        def classify(self, product_text, candidates):
            self.failure_count += 1
            return None

    return {"failure": FakeFailure(), "success": FakeSuccess()}


@pytest.fixture(autouse=True)
def isolate_each_test(monkeypatch, tmp_path):
    """Isola cache por teste usando diretório temporário."""
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_CACHE_TTL_DAYS", "30")
    import importlib

    import parsers.llm_cache as lc

    importlib.reload(lc)
    monkeypatch.setattr(lc, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(lc, "_CACHE_DB", tmp_path / "llm_cache.db")
    yield


@pytest.fixture(autouse=True)
def enable_feature(monkeypatch):
    monkeypatch.setattr("services.config.get", lambda k, d=None: True)


def test_classify_sync_hits_first_strategy(mock_strategies):
    """Se primeira strategy succeita, retorna imediatamente."""
    from parsers.llm_classifier import LLMClassifier

    strategies = [mock_strategies["success"]]
    clf = LLMClassifier(strategies)
    result = clf.classify_sync("Any", [{"canonical_name": "x"}])
    assert result is not None
    assert result["match"] is True


def test_classify_sync_skips_failed_and_picks_next(mock_strategies):
    """Falha na primeira, sucesso na segunda → fallback chain."""
    from parsers.llm_classifier import LLMClassifier

    strategies = [mock_strategies["failure"], mock_strategies["success"]]
    clf = LLMClassifier(strategies)
    result = clf.classify_sync("Any", [{"canonical_name": "x"}])
    assert result["match"] is True


def test_classify_sync_all_strategies_fail_returns_fallback():
    """Se todas falham, retorna graceful degradation."""
    from parsers.llm_classifier import LLMClassifier

    class AllFail:
        provider_name = "all_fail"
        failure_count = 0

        def classify(self, *a, **k):
            return None

    clf = LLMClassifier([AllFail()])
    result = clf.classify_sync("Any", [{"canonical_name": "x"}])
    assert result["match"] is False
    assert result["provider"] == "fallback"
    assert result["ingredient"] is None
    assert result["confidence"] == 0.0


def test_classify_sync_disabled_by_feature_flag(monkeypatch):
    """Se flag desativada, retorna None sem processar."""
    monkeypatch.setattr("services.config.get", lambda k, d=None: False)
    from parsers.llm_classifier import LLMClassifier

    clf = LLMClassifier()
    assert clf.classify_sync("Any", [{"canonical_name": "x"}]) is None


def test_classify_sync_empty_candidates():
    """Sem candidatos → fallback seguro."""
    from parsers.llm_classifier import LLMClassifier

    clf = LLMClassifier()
    result = clf.classify_sync("product", [])
    assert result["provider"] == "fallback"


def test_classify_sync_uses_cache_when_present(monkeypatch):
    """Se decisão já está no cache SQLite, retorna cache e não chama strategies."""
    cached_decision = {
        "match": True,
        "ingredient": "from_cache",
        "confidence": 0.99,
        "reason": "cached",
        "provider": "cache",
    }
    from parsers import llm_cache as lc

    lc.set_cache("cached product", "", cached_decision)

    class ShouldNotUse:
        provider_name = "should_not_use"
        called = False

        def classify(self, *a, **k):
            self.called = True
            return None

    strat = ShouldNotUse()
    from parsers.llm_classifier import LLMClassifier

    clf = LLMClassifier([strat])
    result = clf.classify_sync("cached product", [{"canonical_name": "x"}])

    assert result is not None
    assert result.get("ingredient") == "from_cache"
    assert strat.called is False, "Cache should short-circuit strategies"


def test_flush_cache_helper():
    """Method exists and returns int."""
    from parsers.llm_classifier import LLMClassifier

    clf = LLMClassifier()
    result = clf.flush_cache()
    assert isinstance(result, (int, type(None)))


def test_legacy_module_level_api():
    """Função `classify` module-level para compatibilidade."""
    with patch("services.config.get", return_value=False):
        from parsers.llm_classifier import classify

        # Quando feature flag está off
        assert classify("p", [{"canonical_name": "x"}]) is None


def test_classifier_propagates_provider_name_in_result():
    """Confirma que o provider name aparece no resultado."""
    from parsers.llm_strategies import LLMResult

    class MyProvider:
        provider_name = "my_provider"

        def classify(self, *a, **k):
            return LLMResult(
                match=True,
                canonical_name="X",
                confidence_score=0.9,
                reason="r",
                provider="my_provider",
            )

    from parsers.llm_classifier import LLMClassifier

    clf = LLMClassifier([MyProvider()])
    result = clf.classify_sync("p", [{"canonical_name": "x"}])
    assert result["provider"] == "my_provider"
