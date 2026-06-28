"""
Matching semântico via embeddings locais (sentence-transformers).
CPU-only, determinístico, cache em disco e suporte a ONNX para performance.
"""

import hashlib
import logging
from pathlib import Path
import numpy as np
from services.types import Ingredient

_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "embedding_cache"
_ONNX_DIR = Path(__file__).resolve().parent.parent / "data" / "onnx_models"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_ONNX_DIR.mkdir(parents=True, exist_ok=True)


class SemanticMatcher:
    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self._model = None
        self._onnx_model = None
        self._ingredient_embeddings: dict[str, np.ndarray] = {}
        self._loaded = False

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _get_onnx_model(self):
        """Load or export the model to ONNX format."""
        if self._onnx_model is not None:
            return self._onnx_model

        onnx_path = _ONNX_DIR / self.model_name.replace("/", "_")
        try:
            from optimum.onnxruntime import ORTModelForFeatureExtraction
            from transformers import AutoTokenizer

            if not onnx_path.exists():
                # Export model to ONNX
                model = ORTModelForFeatureExtraction.from_pretrained(self.model_name, export=True)
                tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                model.save_pretrained(str(onnx_path))
                tokenizer.save_pretrained(str(onnx_path))
            else:
                model = ORTModelForFeatureExtraction.from_pretrained(str(onnx_path))
                tokenizer = AutoTokenizer.from_pretrained(str(onnx_path))

            self._onnx_model = (model, tokenizer)
            return self._onnx_model
        except Exception as e:
            logging.getLogger(__name__).warning("ONNX load failed, falling back to PyTorch: %s", e)
            return None

    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def _get_cached_embedding(self, text: str) -> np.ndarray | None:
        path = _CACHE_DIR / f"{self._cache_key(text)}.npy"
        if path.exists():
            return np.load(path)
        return None

    def _cache_embedding(self, text: str, embedding: np.ndarray):
        path = _CACHE_DIR / f"{self._cache_key(text)}.npy"
        np.save(path, embedding)

    def get_embedding(self, text: str) -> np.ndarray:
        cached = self._get_cached_embedding(text)
        if cached is not None:
            return cached

        onnx_data = self._get_onnx_model()
        if onnx_data:
            model, tokenizer = onnx_data
            inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
            outputs = model(**inputs)
            # Mean pooling of token embeddings
            emb = outputs.last_hidden_state.mean(dim=1).detach().numpy()[0]
        else:
            model = self._get_model()
            emb = model.encode(text)

        self._cache_embedding(text, emb)
        return emb

    def load_ingredients(self, ingredients: list[Ingredient]):
        for ing in ingredients:
            texts = [ing["canonical_name"]] + ing.get("aliases", []) + ing.get("search_terms", [])
            for t in texts:
                self._ingredient_embeddings[t] = self.get_embedding(t)
        self._loaded = True

    def get_similarity(self, product_text: str, ingredient: Ingredient) -> float:
        from services.config import get as get_config

        if not get_config("features.ai.semantic_matcher", True):
            return 0.0
        if not self._loaded:
            self.load_ingredients([ingredient])

        prod_emb = self.get_embedding(product_text)
        texts = [ingredient["canonical_name"]] + ingredient.get("aliases", [])

        embeddings = []
        for t in texts:
            emb = self._ingredient_embeddings.get(t)
            if emb is None:
                emb = self.get_embedding(t)
                self._ingredient_embeddings[t] = emb
            embeddings.append(emb)

        if not embeddings:
            return 0.0

        embs_matrix = np.array(embeddings)
        norms = np.linalg.norm(embs_matrix, axis=1)
        prod_norm = np.linalg.norm(prod_emb)

        if prod_norm == 0:
            return 0.0

        similarities = np.dot(embs_matrix, prod_emb) / (norms * prod_norm)
        return float(np.max(similarities))

    def combined_score(self, rapidfuzz_score: float, semantic_score: float) -> float:
        return 0.6 * (rapidfuzz_score / 100.0) + 0.4 * semantic_score


_matcher_instance: SemanticMatcher | None = None


def get_matcher() -> SemanticMatcher:
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = SemanticMatcher()
    return _matcher_instance
