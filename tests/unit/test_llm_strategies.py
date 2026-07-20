"""
Testes unitários para parsers/llm_strategies.py

Cobre:
- JSON Mode parsing (response_format)
- Circuit Breaker (failure tracking e cooldown)
- Mock HTTP (httpx_mock)
- Cada provider (Groq, OpenRouter, HuggingFace)
- Safe parse de respostas mal-formadas
"""

from unittest.mock import MagicMock, patch

import pytest

# ====================================================================
# Fixtures
# ====================================================================


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test_groq_key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test_or_key")
    monkeypatch.setenv("HUGGINGFACE_API_KEY", "test_hf_key")
    monkeypatch.setenv("LLM_CB_THRESHOLD", "3")
    monkeypatch.setenv("LLM_CB_COOLDOWN", "1")  # short for tests
    monkeypatch.setenv("LLM_TIMEOUT", "5")


# ====================================================================
# CircuitBreaker behavior
# ====================================================================


def test_circuit_opens_after_n_failures(mock_env):
    from parsers.llm_strategies import GroqStrategy

    g = GroqStrategy()
    assert g.is_circuit_open() is False
    g.record_failure()
    g.record_failure()
    g.record_failure()
    assert g.is_circuit_open() is True


def test_circuit_resets_after_cooldown(mock_env):
    from parsers.llm_strategies import GroqStrategy

    g = GroqStrategy()
    g.failure_count = 3  # threshold (LLM_CB_THRESHOLD=3 via mock_env)
    g.last_failure_ts = 0  # way in the past → cooldown expired
    # Cooldown expirado permite UMA tentativa (half-open); o breaker só fecha de
    # fato em record_success(). Não zera cegamente o contador.
    assert g.is_circuit_open() is False


def test_open_circuit_immediately_on_429(mock_env, monkeypatch):
    """Groq 429 deve abrir o breaker IMEDIATAMENTE e ceder ao próximo provider."""
    from parsers.llm_strategies import GroqStrategy

    g = GroqStrategy()
    assert g.is_circuit_open() is False
    g.open_circuit()
    assert g.is_circuit_open() is True


def test_open_circuit_applies_aggressive_backoff(mock_env, monkeypatch):
    """Cada reabertura consecutiva dobra o cooldown (capado em LLM_CB_COOLDOWN_MAX)."""
    import parsers.llm_strategies as mod

    monkeypatch.setattr(mod, "_get_cooldown_seconds", lambda: 10)
    monkeypatch.setattr(mod, "_get_cooldown_max", lambda: 100)
    monkeypatch.setattr(mod, "_get_cooldown_growth", lambda: 2.0)
    from parsers.llm_strategies import GroqStrategy

    g = GroqStrategy()
    g.open_circuit()  # 1ª abertura → 10 * 2^1 = 20
    assert g._cooldown_seconds == 20
    g.open_circuit()  # 2ª → 10 * 2^2 = 40
    assert g._cooldown_seconds == 40
    g.open_circuit()  # 3ª → 10 * 2^3 = 80
    assert g._cooldown_seconds == 80
    g.open_circuit()  # 4ª → 10 * 2^4 = 160, capado em 100
    assert g._cooldown_seconds == 100


def test_open_circuit_resets_on_success(mock_env, monkeypatch):
    """Um sucesso real zera o backoff e o contador de aberturas."""
    import parsers.llm_strategies as mod

    monkeypatch.setattr(mod, "_get_cooldown_seconds", lambda: 10)
    from parsers.llm_strategies import GroqStrategy

    g = GroqStrategy()
    g.open_circuit()
    assert g._consecutive_openings == 1
    g.record_success()
    assert g._consecutive_openings == 0
    assert g._cooldown_seconds == 10
    assert g.is_circuit_open() is False


def test_groq_429_opens_circuit(mock_env):
    """Classify com 429 deve abrir o breaker (não só incrementar contador)."""
    from parsers.llm_strategies import GroqStrategy

    g = GroqStrategy()
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.raise_for_status = MagicMock()
    with patch("httpx.Client.post", return_value=mock_response):
        result = g.classify("anything", [{"canonical_name": "x"}])
    assert result is None
    assert g.is_circuit_open() is True
    assert g._consecutive_openings >= 1


def test_groq_open_circuit_skips_http_call(mock_env):
    """Regressão: com o breaker ABERTO, classify deve pular a chamada HTTP.

    Antes, o check `is_circuit_open()` estava em dead code (após um return no
    bloco de api_key), então o breaker aberto era ignorado e o Groq batia na
    API tomando 429 repetidos. Este teste garante que a chamada é pulada.
    """
    from parsers.llm_strategies import GroqStrategy

    g = GroqStrategy()
    g.open_circuit()  # força breaker aberto
    assert g.is_circuit_open() is True

    with patch("httpx.Client.post") as mock_post:
        result = g.classify("anything", [{"canonical_name": "x"}])

    assert result is None
    mock_post.assert_not_called()


def test_record_success_resets_counter(mock_env):
    from parsers.llm_strategies import GroqStrategy

    g = GroqStrategy()
    g.record_failure()
    g.record_failure()
    g.record_success()
    g.record_failure()
    g.record_failure()
    # 2 failures < 3 threshold → not open
    assert g.is_circuit_open() is False


# ====================================================================
# Safe parse
# ====================================================================


def test_safe_parse_basic_json():
    from parsers.llm_strategies import GroqStrategy

    s = GroqStrategy()
    result = s._safe_parse('{"match": true, "canonical_name": "leite condensado"}')
    assert result["match"] is True
    assert result["canonical_name"] == "leite condensado"


def test_safe_parse_strips_markdown_fence():
    from parsers.llm_strategies import GroqStrategy

    s = GroqStrategy()
    content = '```json\n{"match": false, "reason": "test"}\n```'
    result = s._safe_parse(content)
    assert result["match"] is False


def test_safe_parse_returns_none_for_invalid():
    from parsers.llm_strategies import GroqStrategy

    s = GroqStrategy()
    assert s._safe_parse("no json here") is None
    assert s._safe_parse("") is None
    assert s._safe_parse("{incomplete") is None


# ====================================================================
# GroqStrategy
# ====================================================================


def test_groq_no_api_key(mock_env, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    from parsers.llm_strategies import GroqStrategy

    g = GroqStrategy()
    result = g.classify("test product", [{"canonical_name": "ing"}])
    assert result is None


def test_groq_success_mocked(mock_env):
    from parsers.llm_strategies import GroqStrategy

    g = GroqStrategy()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"match": true, "canonical_name": "leite condensado", '
                    '"confidence_score": 0.92, "reason": "exact product"}'
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client.post", return_value=mock_response):
        result = g.classify("Leite Condensado Moça", [{"canonical_name": "leite condensado"}])
    assert result is not None
    assert result.match is True
    assert result.canonical_name == "leite condensado"
    assert result.confidence_score == 0.92
    assert result.provider == "groq"


def test_groq_rate_limit_429(mock_env):
    from parsers.llm_strategies import GroqStrategy

    g = GroqStrategy()

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client.post", return_value=mock_response):
        result = g.classify("anything", [{"canonical_name": "x"}])
    assert result is None
    assert g.failure_count >= 1


def test_groq_500_error(mock_env):
    from parsers.llm_strategies import GroqStrategy

    g = GroqStrategy()
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client.post", return_value=mock_response):
        result = g.classify("anything", [{"canonical_name": "x"}])
    assert result is None
    assert g.failure_count >= 1


def test_groq_invalid_json_response(mock_env):
    from parsers.llm_strategies import GroqStrategy

    g = GroqStrategy()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "this is not json"}}]}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client.post", return_value=mock_response):
        result = g.classify("x", [{"canonical_name": "y"}])
    assert result is None


# ====================================================================
# OpenRouterStrategy
# ====================================================================


def test_openrouter_no_api_key(mock_env, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    from parsers.llm_strategies import OpenRouterStrategy

    o = OpenRouterStrategy()
    result = o.classify("test", [{"canonical_name": "x"}])
    assert result is None


def test_openrouter_success(mock_env):
    from parsers.llm_strategies import OpenRouterStrategy

    o = OpenRouterStrategy()
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"match": true, "canonical_name": "chocolate", "confidence_score": 0.8, "reason": "test"}'
                }
            }
        ]
    }
    mock.raise_for_status = MagicMock()
    with patch("httpx.Client.post", return_value=mock):
        result = o.classify("Chocolate", [{"canonical_name": "chocolate"}])
    assert result is not None
    assert result.provider == "openrouter"


def test_openrouter_rate_limit(mock_env):
    from parsers.llm_strategies import OpenRouterStrategy

    o = OpenRouterStrategy()
    mock = MagicMock()
    mock.status_code = 429
    mock.raise_for_status = MagicMock()
    with patch("httpx.Client.post", return_value=mock):
        result = o.classify("x", [{"canonical_name": "y"}])
    assert result is None
    assert o.failure_count >= 1


def test_openrouter_default_model_is_free_router(mock_env):
    """Slug fixo (mixtral-8x7b) foi descontinuado e retorna 404; o default deve
    ser o roteador `openrouter/free` (auto-seleciona modelo free disponivel)."""
    from parsers.llm_strategies import OpenRouterStrategy

    o = OpenRouterStrategy()
    assert o.model == "openrouter/free"


def test_openrouter_404_opens_circuit(mock_env):
    """4xx persistente (ex.: 404 modelo inexistente) deve ABRIR o breaker para
    nao martelar o endpoint a cada produto — o erro so se resolve corrigindo a
    config, nao em retry. Regressao do scrape 29582782313 (OpenRouter 404 loop)."""
    from parsers.llm_strategies import OpenRouterStrategy

    o = OpenRouterStrategy()
    mock = MagicMock()
    mock.status_code = 404
    mock.raise_for_status = MagicMock()
    with patch("httpx.Client.post", return_value=mock):
        result = o.classify("x", [{"canonical_name": "y"}])
    assert result is None
    # Breaker aberto → proxima chamada nem faz request (economiza a janela).
    assert o.is_circuit_open()


# ====================================================================
# HuggingFaceStrategy
# ====================================================================


def test_huggingface_no_api_key(mock_env, monkeypatch):
    monkeypatch.setenv("HUGGINGFACE_API_KEY", "")
    from parsers.llm_strategies import HuggingFaceStrategy

    h = HuggingFaceStrategy()
    result = h.classify("o que é", [{"canonical_name": "x"}])
    assert result is None


def test_huggingface_success(mock_env):
    from parsers.llm_strategies import HuggingFaceStrategy

    h = HuggingFaceStrategy()
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"match": false, "canonical_name": "", "confidence_score": 0.1, "reason": "no match"}'
                }
            }
        ]
    }
    mock.raise_for_status = MagicMock()
    with patch("httpx.Client.post", return_value=mock):
        result = h.classify("o que é açúcar", [{"canonical_name": "açúcar"}])
    assert result is not None
    assert result.match is False
    assert result.provider == "huggingface"


def test_huggingface_401_unauthorized(mock_env):
    from parsers.llm_strategies import HuggingFaceStrategy

    h = HuggingFaceStrategy()
    mock = MagicMock()
    mock.status_code = 401
    mock.raise_for_status = MagicMock()
    with patch("httpx.Client.post", return_value=mock):
        r = h.classify("x", [{"canonical_name": "y"}])
    assert r is None
    assert h.failure_count >= 1  # still records failure for opacity


def test_openrouter_api_error_envelope_opens_circuit(mock_env):
    """Resposta {"error": ...} (quota/config) deve ABRIR o breaker e ceder,
    nao apenas contar como falha de parse pontual."""
    from parsers.llm_strategies import OpenRouterStrategy

    o = OpenRouterStrategy()
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"error": {"message": "quota exceeded", "type": "insufficient_quota"}}
    mock.raise_for_status = MagicMock()
    with patch("httpx.Client.post", return_value=mock):
        r = o.classify("x", [{"canonical_name": "y"}])
    assert r is None
    assert o.is_circuit_open(), "envelope de erro deve abrir o circuit breaker"


def test_openrouter_200_but_no_choices_still_parsed(mock_env):
    """200 com payload inesperado mas sem 'error' nem 'choices' -> parse falha
    (record_failure), nao abre breaker."""
    from parsers.llm_strategies import OpenRouterStrategy

    o = OpenRouterStrategy()
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"unexpected": "shape"}
    mock.raise_for_status = MagicMock()
    with patch("httpx.Client.post", return_value=mock):
        r = o.classify("x", [{"canonical_name": "y"}])
    assert r is None
    assert not o.is_circuit_open()
    assert o.failure_count >= 1


def test_huggingface_network_error_opens_circuit(mock_env):
    """DNS/rede quebrada (ConnectError) deve ABRIR o breaker imediatamente e ceder
    ao proximo provider, em vez de martelar um host inalcançavel por 3 falhas."""
    import httpx
    from parsers.llm_strategies import HuggingFaceStrategy

    h = HuggingFaceStrategy()
    with patch("httpx.Client.post", side_effect=httpx.ConnectError("getaddrinfo failed")):
        r = h.classify("x", [{"canonical_name": "y"}])
    assert r is None
    assert h.is_circuit_open(), "erro de rede deve abrir o circuit breaker"
    assert h._consecutive_openings >= 1


def test_huggingface_timeout_opens_circuit(mock_env):
    import httpx
    from parsers.llm_strategies import HuggingFaceStrategy

    h = HuggingFaceStrategy()
    with patch("httpx.Client.post", side_effect=httpx.TimeoutException("timed out")):
        r = h.classify("x", [{"canonical_name": "y"}])
    assert r is None
    assert h.is_circuit_open()


def test_classifier_falls_back_when_all_providers_fail(mock_env):
    """Quando todos os providers estao configurados mas falham (circuit open),
    o LLMClassifier deve retornar um fallback seguro (match=False) e NUNCA crashar."""
    import parsers.llm_strategies as mod
    from parsers.llm_classifier import LLMClassifier

    # Forca todos os providers com breaker aberto (simulando 429 global).
    strategies = []
    for s in [mod.GroqStrategy(), mod.OpenRouterStrategy(), mod.HuggingFaceStrategy()]:
        s.open_circuit()
        strategies.append(s)

    clf = LLMClassifier(strategies=strategies)
    result = clf.classify_sync("Leite Condensado", [{"canonical_name": "leite condensado"}])
    assert result is not None
    assert result["match"] is False
    assert result["provider"] == "fallback"
