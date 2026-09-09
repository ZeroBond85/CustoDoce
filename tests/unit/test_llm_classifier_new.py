"""
Testes unitários para parsers/llm_classifier.py (REFATORADO - Fase 4.8)

O LLM classifier está DESABILITADO via feature flag (ai.llm_classifier: false).
Estes testes validam o comportamento quando a flag está OFF e os comportamentos
seguros (fallback) quando está ON mas sem candidatos.

Nota: os testes patcham ``services.config.get_feature`` (a função consultada por
``classify_sync`` via import local) — patch em ``services.config.get`` NÃO
funciona porque o override lookup de ``get_feature`` retornaria o fallback
``True`` do mock e ligaria o LLM indevidamente.
"""


def _flag_off(monkeypatch):
    monkeypatch.setattr("services.config.get_feature", lambda *_a, **_k: False)


def _flag_on(monkeypatch):
    monkeypatch.setattr("services.config.get_feature", lambda *_a, **_k: True)


def test_classify_sync_disabled_by_feature_flag(monkeypatch):
    """Se flag desativada, retorna None sem processar."""
    _flag_off(monkeypatch)
    from parsers.llm_classifier import LLMClassifier

    clf = LLMClassifier()
    assert clf.classify_sync("Any", [{"canonical_name": "x"}]) is None


def test_classify_sync_empty_candidates(monkeypatch):
    """Flag ON sem candidatos → fallback seguro (nunca toca rede)."""
    _flag_on(monkeypatch)
    from parsers.llm_classifier import LLMClassifier

    clf = LLMClassifier()
    result = clf.classify_sync("product", [])
    assert result is not None
    assert result["provider"] == "fallback"


def test_classify_sync_empty_candidates_with_flag_off(monkeypatch):
    """Sem candidatos e flag off → None (flag tem precedência sobre o fallback)."""
    _flag_off(monkeypatch)
    from parsers.llm_classifier import LLMClassifier

    clf = LLMClassifier()
    assert clf.classify_sync("product", []) is None


def test_legacy_module_level_api(monkeypatch):
    """Função `classify` module-level para compatibilidade."""
    _flag_off(monkeypatch)
    from parsers.llm_classifier import classify

    # Quando feature flag está off
    assert classify("p", [{"canonical_name": "x"}]) is None


def test_llm_preflight_logs_when_providers_down(monkeypatch, caplog):
    """Verifica se o preflight loga quando provedores estão down."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    from services.llm_preflight import llm_preflight

    # force=True ignora cache em memória (definido por testes anteriores)
    result = llm_preflight(force=True)
    assert result["groq"] is False
    assert result["openrouter"] is False
