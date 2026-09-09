"""Testes para o módulo de LLM preflight."""

import os
import time
from unittest.mock import patch, MagicMock


from services.llm_preflight import (
    _load_cache,
    _save_cache,
    _probe_provider,
    llm_preflight,
    get_best_provider,
    mark_deprecated,
    _get_cached,
)


class TestLLMPreflight:
    """Testes unitários para o módulo de preflight LLM."""

    def setup_method(self):
        # Limpar env var entre testes
        if "LLM_PREFLIGHT" in os.environ:
            del os.environ["LLM_PREFLIGHT"]
        # Garantir chaves de API para testes
        os.environ.setdefault("GROQ_API_KEY", "test-key")
        os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

    def teardown_method(self):
        if "LLM_PREFLIGHT" in os.environ:
            del os.environ["LLM_PREFLIGHT"]

    def test_load_save_cache(self):
        """Testa carregar e salvar cache."""
        _save_cache({"test": {"ok": True, "ts": time.time()}})
        cache = _load_cache()
        assert "test" in cache
        assert cache["test"]["ok"] is True

    def test_probe_provider_no_api_key(self):
        """Testa probe quando não há API key."""
        os.environ.pop("GROQ_API_KEY", None)
        result = _probe_provider("groq")
        assert result["ok"] is False
        assert result["error"] == "no_api_key"

    @patch("services.llm_preflight.httpx.Client")
    def test_probe_provider_success(self, mock_client):
        """Testa probe bem-sucedido."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "qwen/qwen3.8-27b"}]}
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp

        result = _probe_provider("groq")
        assert result["ok"] is True
        assert result["version"] == "qwen/qwen3.8-27b"

    @patch("services.llm_preflight.httpx.Client")
    def test_probe_provider_400(self, mock_client):
        """Testa erro 400 (modelo removido)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp

        result = _probe_provider("groq")
        assert result["ok"] is False
        assert result["error"] == "bad_request"

    @patch("services.llm_preflight.httpx.Client")
    def test_probe_provider_429(self, mock_client):
        """Testa erro 429 (cooldown)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp

        result = _probe_provider("groq")
        assert result["ok"] is False
        assert result["error"] == "cooldown_429"

    @patch("services.llm_preflight.httpx.Client")
    def test_probe_provider_timeout(self, mock_client):
        """Testa timeout."""
        import httpx
        mock_client.return_value.__enter__.return_value.get.side_effect = httpx.TimeoutException("timeout")

        result = _probe_provider("groq")
        assert result["ok"] is False
        assert result["error"] == "timeout"

    @patch("services.llm_preflight._probe_provider")
    def test_llm_preflight_cache_reuse(self, mock_probe):
        """Testa reuso de cache (não chama probe se cache válido)."""
        mock_probe.return_value = {"ok": True, "version": "test", "error": None, "ts": time.time()}

        # Primeira chamada
        r1 = llm_preflight(["groq"])
        # Segunda chamada (deve reusar cache)
        r2 = llm_preflight(["groq"])

        assert r1 == r2 == {"groq": True}
        assert mock_probe.call_count == 1  # Probe chamado apenas uma vez

    @patch("services.llm_preflight._probe_provider")
    def test_llm_preflight_force(self, mock_probe):
        """Testa force=True ignora cache."""
        mock_probe.return_value = {"ok": True, "version": "test", "error": None, "ts": time.time()}

        llm_preflight(["groq"], force=False)
        llm_preflight(["groq"], force=True)

        assert mock_probe.call_count == 2  # Force=True força nova chamada

    @patch("services.llm_preflight._probe_provider")
    def test_get_best_provider(self, mock_probe):
        """Testa seleção do melhor provedor."""
        mock_probe.side_effect = [
            {"ok": False, "error": "down", "version": None, "ts": time.time()},  # groq
            {"ok": True, "version": "test", "error": None, "ts": time.time()},    # openrouter
        ]

        best = get_best_provider(["groq", "openrouter"])
        assert best == "openrouter"

    @patch("services.llm_preflight._probe_provider")
    def test_get_best_provider_all_down(self, mock_probe):
        """Testa quando todos estão down."""
        mock_probe.return_value = {"ok": False, "error": "down", "version": None, "ts": time.time()}

        best = get_best_provider(["groq", "openrouter"])
        assert best is None

    @patch("services.llm_preflight._probe_provider")
    def test_mark_deprecated(self, mock_probe):
        """Testa marcação manual de provedor como deprecated."""
        mock_probe.return_value = {"ok": True, "version": "test", "error": None, "ts": time.time()}

        # Primeiro, provedor OK
        get_best_provider(["groq"])
        mark_deprecated("groq")
        best = get_best_provider(["groq"])
        assert best is None

    def test_cached_functions(self):
        """Testa funções de cache interno."""
        _save_cache({"llm_preflight_test": {"ok": True, "ts": time.time()}})
        cached = _get_cached("test")
        assert cached is not None
        assert cached["ok"] is True
