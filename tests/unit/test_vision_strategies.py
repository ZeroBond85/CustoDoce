"""Tests for parsers/vision_strategies.py."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from parsers.vision_strategies import (
    VisionResult,
    _safe_parse,
    GroqVisionStrategy,
    OpenRouterVisionStrategy,
    HFVisionStrategy,
    get_vision_chain,
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


class TestHFVisionStrategy:
    def test_init_sets_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            vision = HFVisionStrategy()
            assert vision.api_key == ""

    def test_init_sets_api_key_from_env(self):
        with patch.dict("os.environ", {"HF_API_KEY": "test-key"}):
            vision = HFVisionStrategy()
            assert vision.api_key == "test-key"


class TestVisionChain:
    def test_get_vision_chain_returns_list(self):
        chain = get_vision_chain()
        assert isinstance(chain, list)
        assert len(chain) >= 1


class TestExtractProductsViaVision:
    def test_extract_products_no_config_returns_none(self):
        with patch.dict("os.environ", {}, clear=True):
            result = extract_products_via_vision(b"fake image")
            assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
