import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from parsers.semantic_matcher import SemanticMatcher


@pytest.fixture
def mock_matcher():
    with patch("sentence_transformers.SentenceTransformer") as mock_st:
        matcher = SemanticMatcher()
        matcher._model = MagicMock()
        matcher._model.encode.side_effect = lambda text: (
            np.array([1.0, 0.0, 0.0]) if "leite" in text.lower()
            else np.array([0.0, 1.0, 0.0])
        )
        matcher._loaded = True
        yield matcher


@pytest.fixture
def mock_matcher_full():
    """Full isolation: bypass cache and ONNX, use mocked PyTorch model."""
    matcher = SemanticMatcher()
    matcher._model = MagicMock()
    matcher._model.encode.side_effect = lambda text: (
        np.array([1.0, 0.0, 0.0]) if "leite" in text.lower()
        else np.array([0.0, 1.0, 0.0])
    )
    matcher._loaded = True
    with (
        patch.object(matcher, "_get_cached_embedding", return_value=None),
        patch.object(matcher, "_get_onnx_model", return_value=None),
    ):
        yield matcher


def test_combined_score():
    matcher = SemanticMatcher()
    # 0.6 * (80/100) + 0.4 * 0.5 = 0.48 + 0.20 = 0.68
    score = matcher.combined_score(80.0, 0.5)
    assert pytest.approx(score) == 0.68


def test_get_similarity_basic(mock_matcher_full):
    ing = {"canonical_name": "Leite Condensado", "aliases": []}
    # Both contain "leite" -> dot product of [1,0,0] and [1,0,0] is 1.0
    sim = mock_matcher_full.get_similarity("Leite de coco", ing)
    assert pytest.approx(sim) == 1.0


def test_get_similarity_different(mock_matcher_full):
    ing = {"canonical_name": "Leite Condensado", "aliases": []}
    # "Chocolate" doesn't contain "leite" -> [0,1,0] dot [1,0,0] is 0.0
    sim = mock_matcher_full.get_similarity("Chocolate amargo", ing)
    assert pytest.approx(sim) == 0.0


def test_get_similarity_disabled():
    with patch("services.config.get", return_value=False):
        matcher = SemanticMatcher()
        ing = {"canonical_name": "Leite", "aliases": []}
        assert matcher.get_similarity("Leite", ing) == 0.0


@pytest.mark.parametrize(
    "text, expected_vec",
    [
        ("Leite", [1.0, 0.0, 0.0]),
        ("Chocolate", [0.0, 1.0, 0.0]),
        ("Torta", [0.0, 1.0, 0.0]),
    ],
)
def test_embedding_mock(mock_matcher_full, text, expected_vec):
    vec = mock_matcher_full.get_embedding(text)
    assert np.array_equal(vec, np.array(expected_vec))


def test_cache_logic(tmp_path):
    # Use a fresh matcher with temporary cache dir
    with patch("parsers.semantic_matcher._CACHE_DIR", tmp_path):
        matcher = SemanticMatcher()
        # Patch both model loading paths: ONNX (may succeed locally) and PyTorch fallback
        with (
            patch.object(matcher, "_get_model") as mock_model,
            patch.object(matcher, "_get_onnx_model", return_value=None),
        ):
            mock_model.return_value = MagicMock()
            mock_model.return_value.encode.return_value = np.array([1, 2, 3])

            # First call: loads model and saves cache
            matcher.get_embedding("test_text")
            assert mock_model.call_count == 1

            # Second call: loads from cache
            matcher.get_embedding("test_text")
            assert mock_model.call_count == 1
