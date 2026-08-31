"""Validação com dados reais do pipeline de match — motor atual (minilm) vs e5-large.

Reproduz a lógica EXATA de `services/collector.py::process_price_match`:
    - `match_ingredient(product, ingredients, threshold=60.0)` (RapidFuzz)
    - semantic -> `combined = 0.6*(rf/100)+0.4*sem`
    - gate de persistência: combined >= 0.80

Engines:
    --engine minilm : motor ATUAL (SemanticMatcher real, ONNX MiniLM, sem prefixos)
    --engine e5     : fastembed intfloat/multilingual-e5-large (prefixos query/passage)

Amostras reais:
    - `prices`  (baseline "já persiste" -> NÃO pode rebaixar < 0.80)
    - `review_queue` status=rejected (rejeitados -> NÃO pode subir >= 0.80)

Métricas:
    - recall/cobertura nos prices (% mantidos >=0.80) — regressão se cair
    - falsos positivos nos rejected (% que subiram >=0.80)
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parsers.matcher import match_ingredient  # noqa: E402
from services.supabase_client import get_service_client  # noqa: E402
from services.types import Ingredient  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")
GATE = 0.80
MAX_SAMPLES = 400


class ScoreEngine:
    name = "base"

    def __init__(self) -> None:
        self.ing_emb: dict[str, np.ndarray] = {}
        self.loaded = False

    def load_ingredients(self, ingredients: list[Ingredient]) -> None:
        raise NotImplementedError

    def semantic(self, raw: str, ing: Ingredient) -> float:
        raise NotImplementedError


class MiniLMEngine(ScoreEngine):
    """Motor ATUAL (baseline): SemanticMatcher real (ONNX MiniLM, pooling mean, sem prefixos)."""

    name = "minilm (atual)"

    def load_ingredients(self, ingredients: list[Ingredient]) -> None:
        from parsers.semantic_matcher import SemanticMatcher

        self.sm = SemanticMatcher()
        self.sm.load_ingredients(ingredients)
        self.loaded = True

    def semantic(self, raw: str, ing: Ingredient) -> float:
        return self.sm.get_similarity(raw, ing)


class E5Engine(ScoreEngine):
    """Proposto: fastembed multilingual-e5-large com prefixos query/passage."""

    name = "e5 (proposto)"

    def __init__(self) -> None:
        super().__init__()
        from fastembed import TextEmbedding

        self.model = TextEmbedding("intfloat/multilingual-e5-large")

    def load_ingredients(self, ingredients: list[Ingredient]) -> None:
        texts: set[str] = set()
        for ing in ingredients:
            texts.add(ing["canonical_name"])
            texts.update(ing["aliases"])
            texts.update(ing["search_terms"])
        text_list = sorted(texts)
        vecs = list(self.model.embed(["passage: " + t for t in text_list], batch_size=32))
        self.ing_emb = {t: np.asarray(v, dtype=np.float32) for t, v in zip(text_list, vecs, strict=True)}
        self.loaded = True

    def _embed_one(self, raw: str) -> np.ndarray:
        return np.asarray(list(self.model.embed(["query: " + raw])), dtype=np.float32)[0]

    def semantic(self, raw: str, ing: Ingredient) -> float:
        prod = self._embed_one(raw)
        texts = [ing["canonical_name"]] + list(ing["aliases"])
        sims = []
        for t in texts:
            iv = self.ing_emb.get(t)
            if iv is None:
                iv = np.asarray(list(self.model.embed(["passage: " + t])), dtype=np.float32)[0]
            denom = float(np.linalg.norm(iv) * np.linalg.norm(prod))
            sims.append(0.0 if denom == 0 else float(np.dot(iv, prod) / denom))
        return max(sims) if sims else 0.0


_ID_COL = {"prices": "ingredient_id", "review_queue": "resolved_ingredient"}
_RQ_REJECTED = {"status": "rejected"}


def load_ingredients(client) -> list[Ingredient]:
    rows = client.table("ingredients").select("canonical_name,aliases,search_terms,active").execute().data or []
    ings: list[Ingredient] = []
    for r in rows:
        if r.get("active") is not True:
            continue
        ings.append(
            {
                "canonical_name": r["canonical_name"],
                "aliases": r.get("aliases") or [],
                "search_terms": r.get("search_terms") or [],
            }
        )
    return ings


def fetch_prices(client) -> list[dict]:
    rows = client.table("prices").select("raw_product").limit(5000).execute().data or []
    out = []
    for r in rows:
        raw = (r.get("raw_product") or "").strip()
        if raw:
            out.append({"raw": raw})
    return out


def fetch_rejected(client) -> list[dict]:
    rows = client.table("review_queue").select("raw_product,resolved_ingredient").eq("status", "rejected").limit(5000).execute().data or []
    out = []
    for r in rows:
        raw = (r.get("raw_product") or "").strip()
        if raw:
            out.append({"raw": raw})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["minilm", "e5"], default="e5")
    ap.add_argument("--samples", type=int, default=MAX_SAMPLES)
    args = ap.parse_args()

    client = get_service_client()
    ingredients = load_ingredients(client)
    print(f"ingredients ativos: {len(ingredients)}")

    prices = random.sample(fetch_prices(client), min(args.samples, len(fetch_prices(client))))
    rejected_all = fetch_rejected(client)
    rejected = random.sample(rejected_all, min(args.samples, len(rejected_all)))
    print(f"amostras: prices={len(prices)} rejected={len(rejected)}")

    eng: ScoreEngine = E5Engine() if args.engine == "e5" else MiniLMEngine()
    print(f"engine: {eng.name}")

    t0 = time.time()
    eng.load_ingredients(ingredients)
    print(f"prepare model: {time.time()-t0:.1f}s")

    # baseline prices: deve continuar >=0.80
    n_prices = 0
    kept = 0
    regressed = 0
    for s in prices:
        ing, rf, _ = match_ingredient(s["raw"], ingredients, threshold=60.0)
        if ing is None:
            continue
        n_prices += 1
        sem = eng.semantic(s["raw"], ing)
        combined = 0.6 * (rf / 100.0) + 0.4 * sem
        if combined >= GATE:
            kept += 1
        else:
            regressed += 1
    keep_pct = 100.0 * kept / n_prices if n_prices else 0.0

    # rejected: não deve subir >=0.80
    fp = 0
    n_red = 0
    promoted_examples: list[tuple[str, str, float, float]] = []
    for s in rejected:
        ing, rf, _ = match_ingredient(s["raw"], ingredients, threshold=60.0)
        if ing is None:
            continue
        n_red += 1
        sem = eng.semantic(s["raw"], ing)
        combined = 0.6 * (rf / 100.0) + 0.4 * sem
        if combined >= GATE:
            fp += 1
            if len(promoted_examples) < 20:
                promoted_examples.append((s["raw"], ing["canonical_name"], sem, combined))
    fp_pct = 100.0 * fp / n_red if n_red else 0.0

    print(f"\n  --- rejected que o motor PROMOVERIA (combined>={GATE:.2f}) ---")
    for raw, canon, sem, comb in promoted_examples:
        print(f"    canon='{canon}' sem={sem:.3f} comb={comb:.3f} | {raw[:70]}")

    # ---- threshold sweep para calibrar gate ----
    print(f"\n  --- VARREDURA DE GATE (engine={eng.name}) ---")
    scores_prices = []
    scores_rejected = []
    for s in prices:
        ing, rf, _ = match_ingredient(s["raw"], ingredients, threshold=60.0)
        if ing is None:
            continue
        sem = eng.semantic(s["raw"], ing)
        scores_prices.append(0.6 * (rf / 100.0) + 0.4 * sem)
    for s in rejected:
        ing, rf, _ = match_ingredient(s["raw"], ingredients, threshold=60.0)
        if ing is None:
            continue
        sem = eng.semantic(s["raw"], ing)
        scores_rejected.append(0.6 * (rf / 100.0) + 0.4 * sem)

    for gate in [0.70, 0.72, 0.74, 0.76, 0.78, 0.80, 0.82, 0.84, 0.86, 0.88, 0.90, 0.92, 0.94, 0.96]:
        recall = sum(1 for x in scores_prices if x >= gate) / len(scores_prices) * 100 if scores_prices else 0
        fp = sum(1 for x in scores_rejected if x >= gate) / len(scores_rejected) * 100 if scores_rejected else 0
        print(f"    gate={gate:.2f} -> recall prices={recall:.1f}%  fp rejected={fp:.1f}%")

    print("\n===== RESULTADO VALIDAÇÃO DADOS REAIS =====")
    print(f"Engine: {eng.name} | gate >= {GATE}")
    print(f"  Baseline prices  : {kept}/{n_prices} mantidos >=0.80 ({keep_pct:.1f}%) | regredidos: {regressed}")
    print(f"  Rejected         : {fp}/{n_red} subiram >=0.80 ({fp_pct:.1f}%) | falsos positivos: {fp}")
    print("  (objetivo: prices alto, rejected baixo)")


if __name__ == "__main__":
    main()
