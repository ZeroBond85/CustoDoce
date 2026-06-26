"""
Matching semântico via embeddings locais (sentence-transformers).
CPU-only, determinístico, cache em disco.
"""

import hashlib
from pathlib import Path
from typing import Optional
import numpy as np

_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "embedding_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

class SemanticMatcher:
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self._model = None
        self._ingredient_embeddings: dict[str, np.ndarray] = {}
        self._loaded = False

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def _get_cached_embedding(self, text: str) -> Optional[np.ndarray]:
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
        model = self._get_model()
        emb = model.encode(text)
        self._cache_embedding(text, emb)
        return emb

    def load_ingredients(self, ingredients: list[dict]):
        for ing in ingredients:
            texts = [ing["canonical_name"]] + ing.get("aliases", []) + ing.get("search_terms", [])
            for t in texts:
                self._ingredient_embeddings[t] = self.get_embedding(t)
        self._loaded = True

    def get_similarity(self, product_text: str, ingredient: dict) -> float:
        from services.config import get as get_config
        if not get_config("features.ai.semantic_matcher", True):
            return 0.0
        if not self._loaded:
            self.load_ingredients([ingredient])
        prod_emb = self.get_embedding(product_text)
        texts = [ingredient["canonical_name"]] + ingredient.get("aliases", [])
        best = 0.0
        for t in texts:
            ing_emb = self._ingredient_embeddings.get(t)
            if ing_emb is None:
                ing_emb = self.get_embedding(t)
                self._ingredient_embeddings[t] = ing_emb
            sim = float(np.dot(prod_emb, ing_emb) / (np.linalg.norm(prod_emb) * np.linalg.norm(ing_emb)))
            if sim > best:
                best = sim
        return best

    def combined_score(self, rapidfuzz_score: float, semantic_score: float) -> float:
        return 0.6 * (rapidfuzz_score / 100.0) + 0.4 * semantic_score

_matcher_instance: Optional[SemanticMatcher] = None

def get_matcher() -> SemanticMatcher:
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = SemanticMatcher()
    return _matcher_instance


