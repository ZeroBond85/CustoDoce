"""Tests for services/scraper_trend_detector.py — Fase C."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.scraper_trend_detector import (
    HARD_FAIL_CONSECUTIVE,
    _consecutive_failures,
    _median_duration,
    _median_items,
    _success_rate,
    compute_trend_score,
)


# ── Helpers ──────────────────────────────────────────────────

def _make_log(status: str = "success", duration: int = 30, items: int = 5, days_ago: int = 0) -> dict:
    started = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    return {
        "status": status,
        "started_at": started,
        "duration_seconds": duration,
        "items_found": items,
        "items_matched": items,
    }


def _logs_n(success: int, fail: int, duration: int = 30, items: int = 5) -> list[dict]:
    logs = [_make_log("success", duration, items, days_ago=i) for i in range(success)]
    logs += [_make_log("error", duration // 2, 0, days_ago=success + i) for i in range(fail)]
    return logs


# ── _success_rate ────────────────────────────────────────────

class TestSuccessRate:
    def test_empty(self) -> None:
        assert _success_rate([]) == 0.0

    def test_all_success(self) -> None:
        assert _success_rate(_logs_n(5, 0)) == 1.0

    def test_all_fail(self) -> None:
        assert _success_rate(_logs_n(0, 5)) == 0.0

    def test_half(self) -> None:
        rate = _success_rate(_logs_n(3, 3))
        assert 0.45 < rate < 0.55


# ── _median_duration / _median_items ─────────────────────────

class TestMedianDuration:
    def test_empty(self) -> None:
        assert _median_duration([]) == 0.0

    def test_single(self) -> None:
        assert _median_duration([_make_log(duration=42)]) == 42.0

    def test_odd(self) -> None:
        logs = [_make_log(duration=d) for d in [10, 30, 20]]
        assert _median_duration(logs) == 20.0


class TestMedianItems:
    def test_empty(self) -> None:
        assert _median_items([]) == 0.0

    def test_normal(self) -> None:
        logs = [_make_log(items=i) for i in [1, 5, 3, 7]]
        assert _median_items(logs) == 4.0


# ── _consecutive_failures ────────────────────────────────────

class TestConsecutiveFailures:
    def test_all_success(self) -> None:
        assert _consecutive_failures(_logs_n(5, 0)) == 0

    def test_first_fail(self) -> None:
        logs = [_make_log("error")] * 3 + [_make_log("success")] * 2
        assert _consecutive_failures(logs) == 3

    def test_hard_fail(self) -> None:
        logs = [_make_log("error")] * HARD_FAIL_CONSECUTIVE
        assert _consecutive_failures(logs) == HARD_FAIL_CONSECUTIVE


# ── compute_trend_score ──────────────────────────────────────

class TestComputeTrendScore:
    def test_identical_windows(self) -> None:
        logs = _logs_n(10, 0, duration=30, items=5)
        result = compute_trend_score(logs, logs)
        assert result["status"] == "normal"
        assert result["trend_score"] == pytest.approx(0.0, abs=0.01)

    def test_degradation_success_rate(self) -> None:
        baseline = _logs_n(10, 0, duration=30, items=5)
        current = _logs_n(2, 8, duration=30, items=5)
        result = compute_trend_score(baseline, current)
        assert result["status"] in ("degraded", "critical")
        assert result["trend_score"] > 0.2

    def test_degradation_duration(self) -> None:
        baseline = _logs_n(10, 0, duration=30, items=5)
        current = _logs_n(10, 0, duration=90, items=5)
        result = compute_trend_score(baseline, current)
        assert result["trend_score"] > 0.1  # duration doubled → ~0.3

    def test_hard_fail_override(self) -> None:
        baseline = _logs_n(10, 0, duration=30, items=5)
        current = [_make_log("error")] * HARD_FAIL_CONSECUTIVE
        result = compute_trend_score(baseline, current)
        assert result["status"] == "critical"
        assert result["trend_score"] >= 0.9

    def test_empty_current(self) -> None:
        baseline = _logs_n(10, 0, duration=30, items=5)
        result = compute_trend_score(baseline, [])
        assert result["status"] == "critical"
        assert result["trend_score"] > 0.5

    def test_empty_both(self) -> None:
        result = compute_trend_score([], [])
        assert result["trend_score"] == 0.0
        assert result["status"] == "normal"

    def test_score_capped_at_1(self) -> None:
        baseline = _logs_n(10, 0, duration=30, items=5)
        current = [_make_log("error")] * 10
        result = compute_trend_score(baseline, current)
        assert result["trend_score"] <= 1.0
