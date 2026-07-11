"""Unit tests for services/price_intelligence.py (Z-score + Isolation Forest).

Usa histórico < 10 amostras para exercer o caminho Z-score (sem treinar/salvar
modelo Isolation Forest em disco).
"""

from __future__ import annotations

from unittest.mock import patch

from services import price_intelligence


def _hist(values, store_id="store-001"):
    return [
        {"ingredient_id": "ing-001", "store_id": store_id, "normalized": {"price_per_kg": v}}
        for v in values
    ]


def test_historical_stats_computes_mean_std():
    with patch.object(price_intelligence, "get_price_history", return_value=_hist([25, 26, 27, 26, 26])):
        stats = price_intelligence.PriceIntelligence().get_historical_stats("ing-001", "store-001")
    assert stats["n"] == 5
    assert abs(stats["mean"] - 26.0) < 1e-6
    assert stats["min"] == 25.0
    assert stats["max"] == 27.0
    assert stats["std"] > 0


def test_historical_stats_insufficient_returns_zeros():
    with patch.object(price_intelligence, "get_price_history", return_value=_hist([26.0])):
        stats = price_intelligence.PriceIntelligence().get_historical_stats("ing-001", "store-001")
    assert stats["n"] == 1
    assert stats["mean"] == 0 and stats["std"] == 0


def test_detect_anomaly_flagged_when_far_from_mean():
    with patch.object(price_intelligence, "get_price_history", return_value=_hist([26, 26, 26, 26, 26])), patch(
        "services.config.get", return_value=True
    ):
        res = price_intelligence.PriceIntelligence().detect_anomaly("ing-001", "store-001", 100.0)
    assert res["is_anomaly"] is True
    assert res["tag"] == "PRECO_ELEVADO"


def test_detect_anomaly_sem_historico():
    with patch.object(price_intelligence, "get_price_history", return_value=_hist([26.0])), patch(
        "services.config.get", return_value=True
    ):
        res = price_intelligence.PriceIntelligence().detect_anomaly("ing-001", "store-001", 100.0)
    assert res["tag"] == "SEM_HISTORICO"
    assert res["is_anomaly"] is False


def test_detect_anomaly_feature_disabled_returns_normal():
    with patch.object(price_intelligence, "get_price_history", return_value=_hist([26, 26, 26])), patch(
        "services.config.get", return_value=False
    ):
        res = price_intelligence.PriceIntelligence().detect_anomaly("ing-001", "store-001", 100.0)
    assert res["tag"] == "NORMAL"
    assert res["is_anomaly"] is False


def test_enrich_prices_tags_each_price():
    prices = [
        {"ingredient_id": "ing-001", "store_id": "store-001", "normalized": {"price_per_kg": 26.0}},
        {"ingredient_id": "ing-001", "store_id": "store-001", "normalized": {"price_per_kg": 27.0}},
    ]
    with patch.object(price_intelligence, "get_price_history", return_value=_hist([24, 25, 26, 27, 28])), patch(
        "services.config.get", return_value=True
    ):
        enriched = price_intelligence.PriceIntelligence().enrich_prices(prices)
    assert len(enriched) == 2
    for p in enriched:
        assert "ai_tags" in p
        assert p["ai_tags"] == ["NORMAL"]
