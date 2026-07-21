"""
Flyer Layout Analyzer - Auto-adapta parâmetros de clustering por layout detectado.

Persiste parâmetros bem-sucedidos em config/flyer_learned_params.json para
melhorar progressivamente a extração em flyers recorrentes.
"""

from __future__ import annotations

import json
import os
import statistics
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

# Config file for learned parameters
LEARNED_CONFIG_PATH = Path("config/flyer_learned_params.json")


@dataclass
class LayoutProfile:
    """Perfil do layout detectado."""
    flyer_type: str
    region_count: int
    price_count: int
    avg_region_per_price: float
    estimated_columns: int
    col_gap_estimate: float
    row_gap_estimate: float
    price_density: float
    dominant_price_x_positions: list[float]
    text_height_stats: dict[str, float]


@dataclass
class ClusteringParams:
    """Parâmetros de clustering para um layout."""
    GAP_THRESHOLD: float
    X_GAP_THRESHOLD: float
    BLOCK_DX: float
    BLOCK_DY_ABOVE: float
    BLOCK_DY_BELOW: float
    BLOCK_MAX_TEXTS: int


DEFAULT_PARAMS = ClusteringParams(
    GAP_THRESHOLD=50.0,
    X_GAP_THRESHOLD=250.0,
    BLOCK_DX=260.0,
    BLOCK_DY_ABOVE=320.0,
    BLOCK_DY_BELOW=40.0,
    BLOCK_MAX_TEXTS=6,
)


def analyze_layout(regions: list[dict], prices: list[Any]) -> LayoutProfile:
    """Analisa o layout do flyer a partir das regiões OCR e preços reconstruídos."""
    if not regions or not prices:
        return LayoutProfile(
            flyer_type="unknown",
            region_count=len(regions),
            price_count=len(prices),
            avg_region_per_price=0,
            estimated_columns=1,
            col_gap_estimate=0,
            row_gap_estimate=0,
            price_density=0,
            dominant_price_x_positions=[],
            text_height_stats={},
        )

    def cx(box): return sum(p[0] for p in box) / 4
    def cy(box): return sum(p[1] for p in box) / 4
    def ch(box): return max(p[1] for p in box) - min(p[1] for p in box)

    price_xs = [cx(p.box) for p in prices]
    price_ys = [cy(p.box) for p in prices]
    text_heights = [ch(r["box"]) for r in regions]

    # Estimate columns - cluster x positions
    price_xs_sorted = sorted(price_xs)
    COL_SEPARATION_THRESHOLD = 80.0
    col_centers: list[float] = []
    for x in price_xs_sorted:
        if not col_centers or x - col_centers[-1] > COL_SEPARATION_THRESHOLD:
            col_centers.append(x)
        else:
            col_centers[-1] = (col_centers[-1] + x) / 2

    estimated_cols = len(col_centers)
    col_gaps = [col_centers[i+1] - col_centers[i] for i in range(len(col_centers)-1)]
    col_gap_median = statistics.median(col_gaps) if col_gaps else 0

    # Row gaps - filter for actual row separations
    price_ys_sorted = sorted(price_ys)
    row_gaps = [price_ys_sorted[i+1] - price_ys_sorted[i] for i in range(len(price_ys_sorted)-1)]
    significant_row_gaps = [g for g in row_gaps if g > 50]
    row_gap_median = statistics.median(significant_row_gaps) if significant_row_gaps else 150

    density = len(prices) / max(len(regions), 1) * 1000

    # Determine flyer type
    if len(regions) > 500 and estimated_cols >= 3 and len(regions) / max(len(prices), 1) > 15:
        flyer_type = "tenda_grid_4col"
    elif len(regions) > 350 and estimated_cols >= 3:
        flyer_type = "roldao_dense_grid"
    elif len(regions) < 150 and density > 80:
        flyer_type = "atacadao_sparse"
    elif len(regions) > 400 and estimated_cols >= 3:
        flyer_type = "generic_dense_grid"
    elif density < 30:
        flyer_type = "sparse_catalog"
    else:
        flyer_type = "unknown"

    return LayoutProfile(
        flyer_type=flyer_type,
        region_count=len(regions),
        price_count=len(prices),
        avg_region_per_price=len(regions) / max(len(prices), 1),
        estimated_columns=max(1, estimated_cols),
        col_gap_estimate=col_gap_median,
        row_gap_estimate=row_gap_median,
        price_density=density,
        dominant_price_x_positions=col_centers,
        text_height_stats={
            "mean": statistics.mean(text_heights) if text_heights else 0,
            "median": statistics.median(text_heights) if text_heights else 0,
            "stdev": statistics.stdev(text_heights) if len(text_heights) > 1 else 0,
            "min": min(text_heights) if text_heights else 0,
            "max": max(text_heights) if text_heights else 0,
        }
    )


def params_for_profile(profile: LayoutProfile) -> ClusteringParams:
    """Gera parâmetros adaptativos baseados no perfil."""
    p = profile

    gap = 50.0
    x_gap = 250.0
    block_dx = 260.0
    block_dy_above = 320.0
    block_dy_below = 40.0
    block_max = 6

    if p.estimated_columns > 4:
        x_gap = max(150.0, 250.0 / (p.estimated_columns / 4.0))
        block_dx = min(300.0, 200.0 + (50.0 * p.estimated_columns))

    if p.row_gap_estimate > 0:
        gap = min(80.0, max(30.0, p.row_gap_estimate * 0.8))
        block_dy_above = min(400.0, max(200.0, p.row_gap_estimate * 2.5))

    if p.price_density > 100:
        gap = max(30.0, gap * 0.7)
        x_gap = max(150.0, x_gap * 0.8)
        block_max = min(4, block_max)
    elif p.price_density < 20:
        gap = min(100.0, gap * 1.3)
        block_max = min(8, block_max + 2)

    avg_text_height = p.text_height_stats.get("median", 20)
    if avg_text_height < 15:
        gap = max(20.0, gap * 0.8)
        x_gap = max(100.0, x_gap * 0.8)
    elif avg_text_height > 30:
        gap = min(100.0, gap * 1.2)
        x_gap = min(400.0, x_gap * 1.2)

    return ClusteringParams(
        GAP_THRESHOLD=gap,
        X_GAP_THRESHOLD=x_gap,
        BLOCK_DX=block_dx,
        BLOCK_DY_ABOVE=block_dy_above,
        BLOCK_DY_BELOW=block_dy_below,
        BLOCK_MAX_TEXTS=block_max,
    )


def load_learned_params() -> dict[str, dict]:
    """Carrega parâmetros aprendidos do disco."""
    if LEARNED_CONFIG_PATH.exists():
        try:
            with open(LEARNED_CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_learned_params(params: dict[str, dict]) -> None:
    """Salva parâmetros aprendidos no disco."""
    LEARNED_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LEARNED_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, ensure_ascii=False)


def get_params_for_store(store_id: str, flyer_type: str) -> ClusteringParams | None:
    """Recupera parâmetros aprendidos para uma loja/tipo."""
    learned = load_learned_params()
    key = f"{store_id}:{flyer_type}"
    if key in learned:
        p = learned[key]
        return ClusteringParams(**p)
    return None


def remember_successful_params(store_id: str, flyer_type: str, params: ClusteringParams, quality_score: float) -> None:
    """Lembra parâmetros que funcionaram bem - aprendizado incremental."""
    learned = load_learned_params()
    key = f"{store_id}:{flyer_type}"

    if key not in learned:
        learned[key] = asdict(params)
        learned[key]["success_count"] = 0
        learned[key]["avg_quality"] = quality_score
    else:
        # Moving average update (learning rate 0.3)
        lr = 0.3
        for field in ["GAP_THRESHOLD", "X_GAP_THRESHOLD", "BLOCK_DX", "BLOCK_DY_ABOVE", "BLOCK_MAX_TEXTS"]:
            old = learned[key][field]
            new = getattr(params, field)
            learned[key][field] = old * (1 - lr) + new * lr

        # Update quality average
        count = learned[key].get("success_count", 0)
        old_avg = learned[key].get("avg_quality", 0.5)
        learned[key]["avg_quality"] = (old_avg * count + quality_score) / (count + 1)

    learned[key]["success_count"] = learned[key].get("success_count", 0) + 1
    save_learned_params(learned)


# Whether to use layout-adaptive parameters (env-controlled)
USE_LAYOUT_ADAPTATION = os.environ.get("FLYER_USE_LAYOUT_ADAPTATION", "1") not in ("0", "false", "False")


def get_adaptive_params_with_learning(regions: list[dict], prices: list[Any], store_id: str = "") -> ClusteringParams | None:
    """
    Obtém parâmetros adaptativos com aprendizado:
    1. Tenta params aprendidos para este store
    2. Senão, analisa layout e gera params otimizados
    3. Fallback para defaults
    """
    if not USE_LAYOUT_ADAPTATION:
        return None

    # Try learned params first
    if store_id:
        try:
            profile = analyze_layout(regions, prices)
            learned = get_params_for_store(store_id, profile.flyer_type)
            if learned and getattr(learned, "success_count", 0) >= 3:
                return learned
        except Exception as exc:  # pragma: no cover - best effort
            import logging
            logging.getLogger(__name__).debug("failed to load learned params: %s", exc)

    # Analyze layout and generate adaptive params
    try:
        profile = analyze_layout(regions, prices)
        return params_for_profile(profile)
    except Exception:
        return None


def evaluate_block_quality(blocks: list[dict]) -> float:
    """Avalia qualidade média dos blocos (0-1)."""
    from parsers.flyer_hybrid import _name_quality
    if not blocks:
        return 0.0
    scores = [_name_quality(" ".join(b.get("texts", []))) for b in blocks]
    return sum(scores) / len(scores)
