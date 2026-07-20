"""Tests for parsers/vision_strategies.py."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

import io

from parsers.vision_strategies import (
    VisionResult,
    _downscale_image,
    _safe_parse,
    GroqVisionStrategy,
    OpenRouterVisionStrategy,
    NvidiaVisionStrategy,
    get_vision_chain,
    _get_cached_chain,
    reset_vision_chain,
    extract_products_via_vision,
)


class TestVisionResult:
    def test_vision_result_creation(self):
        result = VisionResult(
            products=[{"name": "Test", "price": 10.0}],
            raw_text="raw",
            provider="test",
        )
        assert len(result.products) == 1
        assert result.provider == "test"


class TestSafeParse:
    def test_safe_parse_valid_json(self):
        content = '{"products": [{"name": "A"}], "confidence": 0.9}'
        result = _safe_parse(content)
        assert result is not None
        assert len(result.products) == 1

    def test_safe_parse_invalid_json(self):
        result = _safe_parse("not json")
        assert result is None

    def test_safe_parse_empty(self):
        result = _safe_parse("")
        assert result is None


class TestGroqVisionStrategy:
    def test_init_sets_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            vision = GroqVisionStrategy()
            assert vision.api_key == ""

    def test_init_sets_api_key_from_env(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
            vision = GroqVisionStrategy()
            assert vision.api_key == "test-key"


class TestOpenRouterVisionStrategy:
    def test_init_sets_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            vision = OpenRouterVisionStrategy()
            assert vision.api_key == ""

    def test_init_sets_api_key_from_env(self):
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            vision = OpenRouterVisionStrategy()
            assert vision.api_key == "test-key"

    def test_default_model_is_gemma_free(self):
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "o"}):
            vision = OpenRouterVisionStrategy()
            assert vision.model == "google/gemma-4-26b-a4b-it:free"

    def test_404_opens_circuit(self):
        """4xx persistente (ex.: 404 modelo inexistente) deve ABRIR o breaker
        para nao martelar o endpoint a cada imagem. Regressao scrape 29582782313."""
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "o"}):
            vision = OpenRouterVisionStrategy()
        resp = MagicMock()
        resp.status_code = 404
        resp.raise_for_status = MagicMock()
        with patch("parsers.vision_strategies.get_client") as gc:
            gc.return_value.post.return_value = resp
            result = vision.extract(b"\xff\xd8\xff\xe0fakejpeg")
        assert result is None
        assert not vision.is_available()


class TestNvidiaVisionStrategy:
    def test_init_sets_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            vision = NvidiaVisionStrategy()
            assert vision.api_key == ""

    def test_init_sets_api_key_from_env(self):
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "test-key"}):
            vision = NvidiaVisionStrategy()
            assert vision.api_key == "test-key"

    def test_default_model_is_llama_vision(self):
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "k"}):
            vision = NvidiaVisionStrategy()
            assert vision.model == "meta/llama-3.2-11b-vision-instruct"
            assert "integrate.api.nvidia.com" in vision.url

    def test_headers_use_bearer(self):
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "k"}):
            vision = NvidiaVisionStrategy()
            assert vision._get_headers()["Authorization"] == "Bearer k"


class TestSafeParseFence:
    def test_parses_markdown_fenced_json(self):
        content = '```json\n{"products": [{"product": "Leite", "price": 4.99}], "raw_text": "x"}\n```'
        result = _safe_parse(content)
        assert result is not None
        assert result.products[0]["product"] == "Leite"

    def test_parses_json_with_surrounding_text(self):
        content = 'Aqui esta:\n{"products": [{"product": "Acucar", "price": 3.5}]}\nfim'
        result = _safe_parse(content)
        assert result is not None
        assert result.products[0]["product"] == "Acucar"

    def test_plain_json_still_works(self):
        result = _safe_parse('{"products": [], "raw_text": "y"}')
        assert result is not None
        assert result.products == []


class TestVisionChain:
    def test_get_vision_chain_returns_list(self):
        chain = get_vision_chain()
        assert isinstance(chain, list)
        assert len(chain) == 5

    def test_chain_order_gemini_nvidia_github_openrouter_tesseract(self):
        names = [s.provider_name for s in get_vision_chain()]
        assert names == ["gemini", "nvidia", "github_models", "openrouter", "tesseract_ocr"]

    def test_chain_marks_has_fallback_except_last(self):
        chain = get_vision_chain()
        assert chain[0]._has_fallback is True
        assert chain[-1]._has_fallback is False

    def test_cached_chain_returns_same_instances(self):
        reset_vision_chain()
        c1 = _get_cached_chain()
        c2 = _get_cached_chain()
        assert c1 is c2
        # mesmo objeto -> o circuit breaker persiste entre imagens da run
        assert [id(s) for s in c1] == [id(s) for s in c2]

    def test_cached_chain_breaker_persists_across_images(self, monkeypatch):
        """Regressao: 429 numa imagem abre o breaker e pula o provider nas proximas."""
        reset_vision_chain()
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        monkeypatch.setenv("GOOGLE_API_KEY", "")
        monkeypatch.setenv("GITHUB_TOKEN", "")
        monkeypatch.setenv("VISION_FAIL_FAST_ON_429", "1")
        monkeypatch.setattr("parsers.vision_strategies.time.sleep", lambda *_: None)
        chain = _get_cached_chain()
        openrouter = next(s for s in chain if s.provider_name == "openrouter")
        client = MagicMock()
        client.post.return_value = _resp429()
        monkeypatch.setattr("parsers.vision_strategies.get_client", lambda: client)
        r1 = openrouter.extract(b"img")
        assert r1 is None
        r2 = openrouter.extract(b"img")
        assert r2 is None
        assert client.post.call_count == 1
        assert openrouter._circuit_open is True


class TestExtractProductsViaVision:
    def test_extract_products_no_config_returns_none(self):
        with patch.dict("os.environ", {}, clear=True):
            result = extract_products_via_vision(b"fake image")
            assert result is None

    def test_nvidia_succeeds_when_gemini_and_github_skip(self, monkeypatch):
        """NVIDIA (2o na chain) e a primeira opcao viavel quando Gemini e
        GitHubModels sao pulados por falta de config."""
        reset_vision_chain()
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        monkeypatch.setenv("NVIDIA_API_KEY", "n")
        monkeypatch.setenv("GOOGLE_API_KEY", "")
        monkeypatch.setenv("GITHUB_TOKEN", "")
        monkeypatch.setenv("GH_MODELS_TOKEN", "")
        monkeypatch.setattr("parsers.vision_strategies.time.sleep", lambda *_: None)

        nvidia_client = MagicMock()
        nvidia_client.post.return_value = _resp(
            200,
            json_body={"choices": [{"message": {"content": '{"products": [{"product": "Leite", "price": 4.0}]}'}}]},
        )

        monkeypatch.setattr("parsers.vision_strategies.get_client", lambda: nvidia_client)

        result = extract_products_via_vision(b"img")
        assert result is not None
        assert result[0]["product"] == "Leite"
        assert nvidia_client.post.call_count == 1

    def test_openrouter_429_opens_breaker_fail_fast(self, monkeypatch):
        """Em 429 com fallback, OpenRouter abre o breaker (fail-fast) em vez de
        obedecer ao Retry-After; a cadeia cede aos providers seguintes."""
        reset_vision_chain()
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        monkeypatch.setenv("NVIDIA_API_KEY", "")
        monkeypatch.setenv("GOOGLE_API_KEY", "")
        monkeypatch.setenv("GITHUB_TOKEN", "")
        monkeypatch.setenv("GH_MODELS_TOKEN", "")
        monkeypatch.setenv("VISION_FAIL_FAST_ON_429", "1")
        monkeypatch.setattr("parsers.vision_strategies.time.sleep", lambda *_: None)

        chain = _get_cached_chain()
        openrouter = next(s for s in chain if s.provider_name == "openrouter")

        or_client = MagicMock()
        or_client.post.return_value = _resp429()
        monkeypatch.setattr("parsers.vision_strategies.get_client", lambda: or_client)

        result = extract_products_via_vision(b"img")
        # OpenRouter 429 -> breaker abre; Tesseract (ultimo) falha em bytes invalidos
        assert result is None
        assert or_client.post.call_count == 1
        assert openrouter._circuit_open is True


def _make_png(width: int, height: int) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 120, 50)).save(buf, format="PNG")
    return buf.getvalue()


class TestDownscaleImage:
    def test_large_image_is_shrunk_and_jpeg(self):
        big = _make_png(2245, 3389)
        out = _downscale_image(big)
        from PIL import Image

        with Image.open(io.BytesIO(out)) as im:
            assert max(im.size) <= 1600
            assert im.format == "JPEG"
        assert len(out) <= 900_000

    def test_invalid_bytes_returns_original(self):
        junk = b"not an image"
        assert _downscale_image(junk) == junk


class TestRetryOn429:
    def _resp(self, status, headers=None, json_body=None):
        return _resp(status, headers, json_body)

    def test_retries_then_succeeds(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "k")
        monkeypatch.setattr("parsers.vision_strategies.VISION_MAX_RETRIES", 2)
        monkeypatch.setattr("parsers.vision_strategies.time.sleep", lambda *_: None)
        strat = GroqVisionStrategy()
        ok = self._resp(
            200,
            json_body={"choices": [{"message": {"content": '{"products": [{"product": "abc", "price": 1.0}]}'}}]},
        )
        client = MagicMock()
        client.post.side_effect = [self._resp(429, headers={"Retry-After": "0"}), ok]
        monkeypatch.setattr("parsers.vision_strategies.get_client", lambda: client)
        result = strat.extract(b"img")
        assert result is not None
        assert result.products[0]["product"] == "abc"
        assert client.post.call_count == 2

    def test_gives_up_after_max_retries(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "k")
        monkeypatch.setattr("parsers.vision_strategies.VISION_MAX_RETRIES", 1)
        monkeypatch.setattr("parsers.vision_strategies.time.sleep", lambda *_: None)
        strat = GroqVisionStrategy()
        client = MagicMock()
        client.post.return_value = self._resp(429, headers={"Retry-After": "0"})
        monkeypatch.setattr("parsers.vision_strategies.get_client", lambda: client)
        result = strat.extract(b"img")
        assert result is None
        assert client.post.call_count == 2


def _resp429(headers=None):
    r = MagicMock()
    r.status_code = 429
    r.headers = headers or {"Retry-After": "30"}
    r.json.return_value = {}
    r.raise_for_status.return_value = None
    return r


def _resp(status, headers=None, json_body=None):
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    r.json.return_value = json_body or {}
    r.raise_for_status.return_value = None
    return r


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
