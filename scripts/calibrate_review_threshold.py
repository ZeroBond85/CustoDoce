"""
scripts/calibrate_review_threshold.py

Calibration harness for the review_queue threshold (features.matcher.review_threshold).

Pulls REAL pending review_queue items, recomputes the matcher stack (RapidFuzz RF +
semantic combined via semantic_matcher), and reports how many items would fall into
each score band. Optional LLM-judge labels a stratified sample to estimate the share
of "useful" matches per band, so the threshold is chosen from data, not intuition.

READ-ONLY: this script never writes to the database. It only reads the review_queue
and, optionally, calls the LLM classifier (which is itself read-only + cached).

Usage:
    python scripts/calibrate_review_threshold.py                    # RF-only combined
    python scripts/calibrate_review_threshold.py --semantic         # include ONNX semantic
    python scripts/calibrate_review_threshold.py --llm-judge        # + LLM labels on sample
    python scripts/calibrate_review_threshold.py --limit 1000

The output is a score-band table plus a recommendation. Decide the threshold by
looking at: share of "useful" items per band AND daily volume.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, cast

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from services.types import Ingredient  # noqa: E402

# Bands to bucket items by combined score (lower-bound inclusive).
# Threshold candidates courtesy for inspection.
BANDS: list[tuple[float, float]] = [
    (0.30, 0.55),
    (0.55, 0.60),
    (0.60, 0.65),
    (0.65, 0.70),
    (0.70, 0.75),
    (0.75, 0.78),
    (0.78, 0.80),
    (0.80, 0.82),
    (0.82, 1.001),
]


def _band_for(combined: float) -> str:
    for lo, hi in BANDS:
        if combined >= lo and combined < hi:
            return f"{lo:.2f}-{hi:.2f}"
    return "out"


def _load_ingredients() -> list[Ingredient]:
    from services.config_db import get_all_ingredients

    return cast("list[Ingredient]", get_all_ingredients(include_inactive=True))


def _load_review_items(limit: int) -> list[dict[str, Any]]:
    from services.review_queue_service import get_review_queue

    return get_review_queue(limit=limit)


def _combined_rf_only(score: float) -> float:
    """When semantic is unavailable, mimic collector using RF/100 as combined floor."""
    return score / 100.0


def _compute_combined(raw_product: str, ingredients: list[Ingredient], use_semantic: bool) -> float:
    """Recompute the collector's combined score for a product, mirroring process_price_match."""
    from parsers.matcher import match_ingredient

    ing, score, _ = match_ingredient(raw_product, ingredients, threshold=0.0)
    combined = score / 100.0

    if use_semantic and ing and score >= 60.0:
        try:
            from parsers.semantic_matcher import get_matcher

            sm = get_matcher()
            semantic = sm.get_similarity(raw_product, ing)
            if semantic > 0.0:
                combined = sm.combined_score(score, semantic)
        except Exception:
            pass  # model unavailable — fall back to RF-only combined
    return combined


def _llm_label_product(raw_product: str, ingredients: list[Ingredient]) -> float | None:
    """Optional judge: LLM returns confidence on the top ingredient candidate.

    Uses GroqStrategy directly (offline judge role) — bypasses the
    features.ai.llm_classifier config gate, since this is a read-only calibration
    harness, not the production gate.
    """
    from parsers.llm_strategies import GroqStrategy
    from parsers.matcher import rank_ingredients

    candidates = rank_ingredients(raw_product, ingredients, top_n=3)
    if not candidates:
        return None
    result = GroqStrategy().classify(raw_product, cast("list[dict[str, Any]]", [c[0] for c in candidates]))
    if result and result.match:
        return result.confidence_score
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Review threshold calibration")
    parser.add_argument("--limit", type=int, default=500, help="Max review items to scan")
    parser.add_argument("--semantic", action="store_true", help="Include ONNX semantic in combined")
    parser.add_argument("--llm-judge", action="store_true", help="LLM-label a stratified sample")
    parser.add_argument("--llm-sample-size", type=int, default=50, help="Per-band LLM sample size")
    args = parser.parse_args()

    ingredients = _load_ingredients()
    items = _load_review_items(args.limit)
    if not items:
        print("Nenhum item pendente na review_queue para calibrar.")
        return

    bands: dict[str, dict[str, Any]] = {}
    for lo, hi in BANDS:
        bands[f"{lo:.2f}-{hi:.2f}"] = {"count": 0, "llm_ok": 0, "llm_total": 0}

    sampled = 0
    for item in items:
        raw_product = (item.get("raw_product") or "").strip()
        if not raw_product:
            continue
        combined = _compute_combined(raw_product, ingredients, args.semantic)
        band = _band_for(combined)
        if band == "out":
            continue
        bands[band]["count"] += 1

        if args.llm_judge and bands[band]["llm_total"] < args.llm_sample_size and sampled < args.limit:
            conf = _llm_label_product(raw_product, ingredients)
            if conf is not None:
                bands[band]["llm_total"] += 1
                if conf >= 0.85:
                    bands[band]["llm_ok"] += 1
                sampled += 1

    print("\n" + "=" * 64)
    print(f"Review Queue Calibration  |  amostra: {len(items)} itens pendentes")
    print(f"combined = {'RF 0.6 + semantic 0.4' if args.semantic else 'RF-only'}")
    print("=" * 64)
    print(f"{'faixa':<12}{'n':>6}{'% do total':>11}{'LLM úteis':>14}")
    print("-" * 64)
    total = sum(b["count"] for b in bands.values()) or 1
    for band, data in bands.items():
        pct = 100.0 * data["count"] / total
        llm_frac = (data["llm_ok"] / data["llm_total"]) if data["llm_total"] else None
        llm_s = f"{llm_frac:.0%} ({data['llm_ok']}/{data['llm_total']})" if llm_frac is not None else "-"
        print(f"{band:<12}{data['count']:>6}{pct:>10.1f}%{llm_s:>14}")
    print("-" * 64)
    print("GATE de persistência (persiste acima deste valor): 0.82")
    print("Itens abaixo do gate que CAEM na fila vivem nas faixas < 0.82.")
    print("=" * 64)

    # Recomendação simples baseada em volume.
    in_queue_under_gate = sum(b["count"] for band, b in bands.items() if float(band.split("-")[0]) < 0.82)
    print(
        f"\n~{in_queue_under_gate} itens da amostra ficariam NA FILA (< gate 0.82)"
        f" = {(100.0 * in_queue_under_gate / len(items)):.1f}% da amostra."
    )
    print(
        "Decida o threshold olhando: (1) % de úteis por faixa (se --llm-judge) "
        "e (2) volume/dia. Mantenha SEMPRE < gate 0.82."
    )


if __name__ == "__main__":
    main()
