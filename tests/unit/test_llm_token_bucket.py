"""Testes do TokenBucket + Smart 429 + Circuit Breaker para LLM Chain."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from parsers.llm_strategies import (
    LLMStrategy,
    _get_cooldown_seconds,
)


class _TestStrategy(LLMStrategy):
    provider_name = "test_provider"

    def __init__(self):
        super().__init__()
        self.api_key = "test_key"

    def is_configured(self) -> bool:
        return True

    def classify(self, product_text: str, candidates: list):
        return None


@pytest.fixture
def strategy():
    return _TestStrategy()


def test_token_bucket_provided(strategy):
    """TokenBucket is initialized in base class."""
    assert strategy._token_bucket is not None
    assert strategy._token_bucket._config.capacity > 0


def test_check_rate_limit_allows_first_call(strategy):
    """First call should always be allowed (bucket starts full)."""
    assert strategy._check_rate_limit() is True


def test_circuit_breaker_starts_closed(strategy):
    """Circuit breaker starts closed (no failures yet)."""
    assert strategy.is_circuit_open() is False


def test_record_failure_opens_after_threshold(strategy):
    """After threshold failures, circuit opens."""
    for _ in range(3):
        strategy.record_failure()
    assert strategy.is_circuit_open() is True


def test_record_success_closes_circuit(strategy):
    """Success resets failure count and closes circuit."""
    for _ in range(3):
        strategy.record_failure()
    assert strategy.is_circuit_open() is True
    strategy.record_success()
    assert strategy.is_circuit_open() is False


def test_open_circuit_server_error(strategy):
    """open_circuit is for server errors, sets cooldown."""
    strategy.open_circuit()
    assert strategy.is_circuit_open() is True
    assert strategy._cooldown_seconds >= _get_cooldown_seconds()


def test_smart_429_returns_true_with_retry_after():
    """_smart_429 returns True when Retry-After is present."""
    strategy = _TestStrategy()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.headers = {"Retry-After": "2"}
    result = strategy._smart_429(mock_resp)
    assert result is True


def test_smart_429_returns_false_without_retry_after():
    """_smart_429 returns False when no Retry-After header."""
    strategy = _TestStrategy()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.headers = {}
    result = strategy._smart_429(mock_resp)
    assert result is False


def test_safe_api_call_returns_response_on_success(strategy):
    """_safe_api_call returns response on 2xx."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None

    with patch("parsers.llm_strategies.get_client") as mock_client:
        mock_client.return_value.post.return_value = mock_resp
        result = strategy._safe_api_call("https://api.test.com", {}, {})
        assert result is mock_resp


def test_safe_api_call_429_fallthrough_no_retry(strategy):
    """429 without Retry-After → None, NO circuit open."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 429
    mock_resp.headers = {}

    with patch("parsers.llm_strategies.get_client") as mock_client:
        mock_client.return_value.post.return_value = mock_resp
        result = strategy._safe_api_call("https://api.test.com", {}, {})
        assert result is None
        # Circuit should NOT be open (429 != server error)
        assert strategy.is_circuit_open() is False


def test_safe_api_call_500_opens_circuit(strategy):
    """500+ opens circuit breaker."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 500
    mock_resp.headers = {}

    with patch("parsers.llm_strategies.get_client") as mock_client:
        mock_client.return_value.post.return_value = mock_resp
        result = strategy._safe_api_call("https://api.test.com", {}, {})
        assert result is None
        assert strategy.is_circuit_open() is True


def test_safe_api_call_timeout_opens_circuit(strategy):
    """Timeout opens circuit breaker."""
    with patch("parsers.llm_strategies.get_client") as mock_client:
        mock_client.return_value.post.side_effect = httpx.TimeoutException("timeout")
        result = strategy._safe_api_call("https://api.test.com", {}, {})
        assert result is None
        assert strategy.is_circuit_open() is True


def test_safe_api_call_503_opens_circuit(strategy):
    """503 opens circuit breaker."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 503
    mock_resp.headers = {}

    with patch("parsers.llm_strategies.get_client") as mock_client:
        mock_client.return_value.post.return_value = mock_resp
        result = strategy._safe_api_call("https://api.test.com", {}, {})
        assert result is None
        assert strategy.is_circuit_open() is True


def test_429_does_not_increment_failure_count(strategy):
    """429 should NOT increment failure_count."""
    initial = strategy.failure_count
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 429
    mock_resp.headers = {}

    with patch("parsers.llm_strategies.get_client") as mock_client:
        mock_client.return_value.post.return_value = mock_resp
        strategy._safe_api_call("https://api.test.com", {}, {})
        assert strategy.failure_count == initial


def test_500_increments_opens_circuit_immediately(strategy):
    """500 should open circuit on FIRST occurrence (not wait for threshold)."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 500
    mock_resp.headers = {}

    with patch("parsers.llm_strategies.get_client") as mock_client:
        mock_client.return_value.post.return_value = mock_resp
        strategy._safe_api_call("https://api.test.com", {}, {})
        assert strategy.failure_count >= 3  # open_circuit sets to threshold


def test_groq_strategy_uses_safe_api_call():
    """GroqStrategy.classify now uses _safe_api_call (not raw post)."""
    from parsers.llm_strategies import GroqStrategy
    import inspect

    source = inspect.getsource(GroqStrategy.classify)
    assert "_safe_api_call" in source
    assert "get_client().post" not in source
