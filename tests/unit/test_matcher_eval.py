"""Tests for the matcher evaluation harness (scripts/evaluate_matcher.py)."""

from pathlib import Path

import pytest

from parsers.matcher import match_ingredient
from scripts.evaluate_matcher import load_golden, load_ingredients

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="session")
def ingredients():
    return load_ingredients()


@pytest.fixture(scope="session")
def golden():
    return load_golden()


def test_golden_file_loads():
    cases = load_golden()
    assert len(cases) >= 30
    for case in cases:
        assert "canonical_name" in case
        assert "expected_match_type" in case
        assert case["expected_match_type"] in ("exato", "proximo_nome", "proximo_apelido", None)


def test_ingredients_loads():
    ings = load_ingredients()
    assert len(ings) >= 20
    for ing in ings:
        assert "canonical_name" in ing


@pytest.mark.parametrize("case_idx", range(5))
def test_first_five_golden_cases(case_idx, ingredients):
    """Smoke test: first 5 golden cases run without error."""
    case = load_golden()[case_idx]
    result, score, match_type = match_ingredient(case["canonical_name"], ingredients)
    actual = result["canonical_name"] if result else None
    if case.get("expected_ingredient") is not None and actual is not None:
        case["actual"] = actual
        case["score"] = score


def test_baseline_metrics_meet_thresholds(ingredients):
    """Verify the current matcher meets minimum thresholds on the golden set.

    O matcher offline (rapidfuzz + exact + exclude_terms) atinge P/R/F1 = 100%
    no golden atual. Os pisos abaixo travam a qualidade com margem de segurança
    para não quebrar em ajustes menores de dados, mas detectam regressões reais.
    """
    from scripts.evaluate_matcher import evaluate

    report = evaluate(check=False, json_output=False)
    assert report["precision"] >= 0.95
    assert report["recall"] >= 0.95
    assert report["f1"] >= 0.95
    assert report["accuracy"] >= 0.95
