"""
scripts/evaluate_matcher.py

E2E matcher evaluation harness: runs the matcher against a golden dataset
and reports precision, recall, F1, match-type accuracy, and per-case breakdown.

Usage:
    python scripts/evaluate_matcher.py                    # full report, exit 0
    python scripts/evaluate_matcher.py --check            # exit 1 if below thresholds
    python scripts/evaluate_matcher.py --json             # JSON output (for CI)

Thresholds (override via env):
    EVAL_PRECISION_MIN=0.90
    EVAL_RECALL_MIN=0.84
    EVAL_F1_MIN=0.87
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GOLDEN_PATH = _REPO_ROOT / "tests" / "fixtures" / "golden_matches.json"


def load_golden() -> list[dict]:
    with open(_GOLDEN_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_ingredients() -> list[dict]:
    import yaml

    with open(_REPO_ROOT / "config" / "ingredients.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    raw = data.get("ingredients", [])
    # Normalize YAML 'canonical' key -> 'canonical_name' (what matcher expects)
    for ing in raw:
        if "canonical" in ing and "canonical_name" not in ing:
            ing["canonical_name"] = ing.pop("canonical")
    return raw


def evaluate(check: bool = False, json_output: bool = False) -> dict:
    sys.path.insert(0, str(_REPO_ROOT))
    from parsers.matcher import match_ingredient

    golden = load_golden()
    ingredients = load_ingredients()

    total = len(golden)
    tp = 0
    fp = 0
    fn = 0
    tn = 0
    type_ok = 0
    cases: list[dict] = []

    for case in golden:
        product = case["canonical_name"]
        expected = case.get("expected_ingredient") or case.get("canonical_name")
        expected_type = case.get("expected_match_type")

        result, score, match_type = match_ingredient(product, ingredients)

        actual = result["canonical_name"] if result else None
        is_match_expected = expected is not None
        is_match_actual = actual is not None

        correct = actual == expected
        type_correct = is_match_actual and is_match_expected and match_type == expected_type

        if is_match_expected and correct:
            tp += 1
        elif is_match_expected and not correct:
            fn += 1
        elif not is_match_expected and is_match_actual:
            fp += 1
        else:
            tn += 1

        if correct:
            type_ok += 1 if type_correct else 0

        cases.append({
            "product": product,
            "expected": expected,
            "actual": actual,
            "score": round(score, 1),
            "match_type": match_type if is_match_actual else None,
            "expected_type": expected_type,
            "correct": correct,
            "type_correct": type_correct,
        })

    pos = sum(1 for c in golden if c.get("expected_ingredient") or c.get("canonical_name"))
    neg = total - pos

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / total if total > 0 else 0.0
    type_accuracy = type_ok / tp if tp > 0 else 0.0

    report = {
        "total": total,
        "positive_cases": pos,
        "negative_cases": neg,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "type_accuracy": round(type_accuracy, 4),
        "cases": cases,
    }

    if json_output:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_report(report)

    if check:
        _check_thresholds(report)

    return report


def _print_report(report: dict):
    print("=" * 60)
    print("Matcher Evaluation Report")
    print("=" * 60)
    print(f"  Total cases:       {report['total']}")
    print(f"  Positive (match):  {report['positive_cases']}")
    print(f"  Negative (no match): {report['negative_cases']}")
    print()
    print(f"  TP: {report['tp']}  FP: {report['fp']}  FN: {report['fn']}  TN: {report['tn']}")
    print()
    print(f"  Precision:  {report['precision']:.2%}")
    print(f"  Recall:     {report['recall']:.2%}")
    print(f"  F1:         {report['f1']:.2%}")
    print(f"  Accuracy:   {report['accuracy']:.2%}")
    print(f"  Type Acc:   {report['type_accuracy']:.2%}")
    print()

    failed = [c for c in report["cases"] if not c["correct"]]
    if failed:
        print(f"  Failed ({len(failed)}):")
        for c in failed:
            print(f"    {c['product']!r}: expected={c['expected']!r} got={c['actual']!r} (score={c['score']})")


def _check_thresholds(report: dict):
    p_min = float(os.environ.get("EVAL_PRECISION_MIN", "0.90"))
    r_min = float(os.environ.get("EVAL_RECALL_MIN", "0.84"))
    f1_min = float(os.environ.get("EVAL_F1_MIN", "0.87"))

    errors = []
    if report["precision"] < p_min:
        errors.append(f"Precision {report['precision']:.2%} < {p_min:.0%}")
    if report["recall"] < r_min:
        errors.append(f"Recall {report['recall']:.2%} < {r_min:.0%}")
    if report["f1"] < f1_min:
        errors.append(f"F1 {report['f1']:.2%} < {f1_min:.0%}")

    if errors:
        print(f"\nTHRESHOLD FAILED: {', '.join(errors)}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\nAll thresholds passed (p>={p_min:.0%} r>={r_min:.0%} f1>={f1_min:.0%}).")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Matcher evaluation harness")
    parser.add_argument("--check", action="store_true", help="Exit 1 if below thresholds")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    evaluate(check=args.check, json_output=args.json)


if __name__ == "__main__":
    main()