"""Testes do SemanticMatcher (fastembed + e5-large)."""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from parsers.semantic_matcher import SemanticMatcher


@pytest.fixture(autouse=True)
def _no_model_download():
    """Patch fastembed.TextEmbedding para nenhum teste de unidade baixar/instanciar
    o modelo real e5-large (rede/perf). O aviso de pooling do fastembed fica
    silenciado já no pyproject filterwarnings; aqui evitamos até a carga."""
    with patch(
        "fastembed.TextEmbedding", return_value=MagicMock()
    ):
        yield


@pytest.fixture
def mock_matcher(_no_model_download):
    """Mock matcher with controlled embeddings."""
    matcher = SemanticMatcher()
    matcher._model = MagicMock()
    # Mock embed to return deterministic vectors based on text content
    def embed_side_effect(texts):
        vecs = []
        for text in texts:
            if "leite" in text.lower():
                vecs.append(np.array([1.0, 0.0, 0.0], dtype=np.float32))
            elif "chocolate" in text.lower():
                vecs.append(np.array([0.0, 1.0, 0.0], dtype=np.float32))
            elif "granulado" in text.lower():
                vecs.append(np.array([0.0, 0.0, 1.0], dtype=np.float32))
            else:
                vecs.append(np.array([0.0, 0.0, 0.0], dtype=np.float32))
        return iter(vecs)
    matcher._model.embed.side_effect = embed_side_effect
    matcher._ingredient_embeddings = {
        "Leite Condensado": np.array([1.0, 0.0, 0.0], dtype=np.float32),
        "Chocolate 50%": np.array([0.0, 1.0, 0.0], dtype=np.float32),
        "Granulado Colorido": np.array([0.0, 0.0, 1.0], dtype=np.float32),
    }
    matcher._loaded = True
    yield matcher


def test_combined_score():
    matcher = SemanticMatcher()
    # 0.6 * (80/100) + 0.4 * 0.5 = 0.48 + 0.20 = 0.68
    score = matcher.combined_score(80.0, 0.5)
    assert pytest.approx(score) == 0.68


def test_get_gate():
    matcher = SemanticMatcher()
    assert matcher.get_gate() == 0.82


def test_get_similarity_basic(mock_matcher):
    ing = {"canonical_name": "Leite Condensado", "aliases": []}
    # Product contains "leite" -> matches ingredient "Leite Condensado" -> sim = 1.0
    sim = mock_matcher.get_similarity("Leite de coco", ing)
    assert pytest.approx(sim) == 1.0


def test_get_similarity_different(mock_matcher):
    ing = {"canonical_name": "Leite Condensado", "aliases": []}
    # "Chocolate" doesn't match "Leite" -> sim = 0.0
    sim = mock_matcher.get_similarity("Chocolate amargo", ing)
    assert pytest.approx(sim) == 0.0


def test_get_similarity_disabled():
    with patch("services.config.get", return_value=False):
        matcher = SemanticMatcher()
        ing = {"canonical_name": "Leite", "aliases": []}
        assert matcher.get_similarity("Leite", ing) == 0.0


