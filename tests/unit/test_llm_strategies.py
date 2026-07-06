"""
Testes unitários para parsers/llm_strategies.py

Cobre:
- JSON Mode parsing (response_format)
- Circuit Breaker (failure tracking e cooldown)
- Mock HTTP (httpx_mock)
- Cada provider (Groq, OpenRouter, HuggingFace)
- Safe parse de respostas mal-formadas
"""

import time
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
    g.record_failure()
    g.record_failure()
    g.record_failure()
    time.sleep(2.5)  # wait beyond cooldown
    assert g.is_circuit_open() is False


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
