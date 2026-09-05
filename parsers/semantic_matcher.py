"""
Matching semântico via embeddings locais (fastembed + e5-large).
CPU-only, determinístico, cache em disco. Prefixos e5: query (produto) / passage (ingredientes).
Gate de persistência recalibrado: 0.82 para e5 (era 0.80 para MiniLM).
"""
import hashlib
import warnings
from pathlib import Path
from typing import cast

from services.types import Ingredient

import numpy as np

# fastembed 0.8.0 emite UserWarning sobre pooling (mean vs CLS) a cada load — já
# validado no benchmark, não afeta acurácia. Filtra p/ zero-warn nos scrapers.
warnings.filterwarnings(
    "ignore",
    message=".*mean pooling instead of CLS.*",
    category=UserWarning,
)

# huggingface_hub (via fastembed) emite UserWarning sobre _HF_HUB_DISABLE_PROGRESS_BARS
# quando o env está set — comportamento desejado, não é problema. Filtra p/ zero-warn.
warnings.filterwarnings(
    "ignore",
    message=".*HF_HUB_DISABLE_PROGRESS_BARS.*",
    category=UserWarning,
)

_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "embedding_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_E5_MODEL = "intfloat/multilingual-e5-large"
_E5_GATE = 0.82  # recalibrado p/ e5 (MiniLM era 0.80)


class SemanticMatcher:
    def __init__(self) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(_E5_MODEL)
        self._ingredient_embeddings: dict[str, np.ndarray] = {}
        self._loaded = False

    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def _get_cached_embedding(self, text: str) -> np.ndarray | None:
        path = _CACHE_DIR / f"{self._cache_key(text)}.npy"
        if path.exists():
            return cast(np.ndarray, np.load(path))
        return None

    def _cache_embedding(self, text: str, embedding: np.ndarray) -> None:
        path = _CACHE_DIR / f"{self._cache_key(text)}.npy"
        np.save(path, embedding)

    def _embed_batch(self, texts: list[str], prefix: str) -> dict[str, np.ndarray]:
        """Embed a batch of texts with given prefix (query:/passage:)."""
        prefixed = [prefix + t for t in texts]
        vecs = list(self._model.embed(prefixed, batch_size=32))
        return {t: np.asarray(v, dtype=np.float32) for t, v in zip(texts, vecs, strict=True)}

    def load_ingredients(self, ingredients: list[Ingredient]) -> None:
        """Pre-embed all ingredient canonical names + aliases + search_terms with passage: prefix."""
        texts: set[str] = set()
        for ing in ingredients:
            texts.add(ing["canonical_name"])
            texts.update(ing.get("aliases") or [])
            texts.update(ing.get("search_terms") or [])
        text_list = sorted(texts)
        self._ingredient_embeddings = self._embed_batch(text_list, "passage: ")
        self._loaded = True

    def get_similarity(self, product_text: str, ingredient: Ingredient) -> float:
        from services.config import get as get_config

        if not get_config("features.ai.semantic_matcher", True):
            return 0.0
        if not self._loaded:
            self.load_ingredients([ingredient])

        # Embed product with query: prefix
        prod_emb = list(self._model.embed(["query: " + product_text]))[0]
        prod_emb = np.asarray(prod_emb, dtype=np.float32)

        texts = [ingredient["canonical_name"]] + cast(list[str], ingredient.get("aliases") or [])
        embeddings: list[np.ndarray] = []
        for t in texts:
            emb = self._ingredient_embeddings.get(t)
            if emb is None:
                emb = self._embed_batch([t], "passage: ")[t]
                self._ingredient_embeddings[t] = emb
            embeddings.append(emb)

        if not embeddings:
            return 0.0

        embs_matrix = np.array(embeddings)
        norms = np.linalg.norm(embs_matrix, axis=1)
        prod_norm = float(np.linalg.norm(prod_emb))

        if prod_norm == 0:
            return 0.0

        similarities = np.dot(embs_matrix, prod_emb) / (norms * prod_norm)
        return float(np.max(similarities))

    def combined_score(self, rapidfuzz_score: float, semantic_score: float) -> float:
        return 0.6 * (rapidfuzz_score / 100.0) + 0.4 * semantic_score

    @staticmethod
    def get_gate() -> float:
        """Gate de persistência recalibrado para e5-large (0.82)."""
        return _E5_GATE


_matcher_instance: SemanticMatcher | None = None


def get_matcher() -> SemanticMatcher:
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = SemanticMatcher()
    return _matcher_instance
