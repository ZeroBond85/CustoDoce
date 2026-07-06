from unittest.mock import patch

from tests.unit.test_services.conftest import MockQueryBuilder, MockSupabaseClient


class TestLongitudinalWinners:
    """Testes para get_longitudinal_winners, get_price_trends, get_cross_ingredient_ranking."""

    def test_longitudinal_winners_returns_empty_when_no_data(self):
        from services.price_service import get_longitudinal_winners

        with patch("services.price_analytics.get_supabase") as mock:
            mock.return_value = MockSupabaseClient(MockQueryBuilder([]))
            result = get_longitudinal_winners()
        assert result == []

    def test_longitudinal_winners_counts_wins(self):
        from services.price_service import get_longitudinal_winners

        data = [
            {
                "ingredient_id": "leite",
                "store_name": "Assai",
                "normalized": {"price_per_kg": 10.0},
                "collected_at": "2026-06-01",
            },
            {
                "ingredient_id": "leite",
                "store_name": "Atacadao",
                "normalized": {"price_per_kg": 12.0},
                "collected_at": "2026-06-01",
            },
            {
                "ingredient_id": "leite",
                "store_name": "Assai",
                "normalized": {"price_per_kg": 11.0},
                "collected_at": "2026-06-02",
            },
            {
                "ingredient_id": "leite",
                "store_name": "Atacadao",
                "normalized": {"price_per_kg": 9.0},
                "collected_at": "2026-06-02",
            },
        ]
        with patch("services.price_analytics.get_supabase") as mock:
            mock.return_value = MockSupabaseClient(MockQueryBuilder(data))
            result = get_longitudinal_winners()
        assert len(result) == 2
        wins = {r["store_name"]: r["wins"] for r in result}
        assert wins["Assai"] == 1  # 2026-06-01
        assert wins["Atacadao"] == 1  # 2026-06-02

    def test_longitudinal_winners_skips_zero_ppk(self):
        from services.price_service import get_longitudinal_winners

        data = [
            {
                "ingredient_id": "leite",
                "store_name": "Assai",
                "normalized": {"price_per_kg": 0},
                "collected_at": "2026-06-01",
            },
        ]
        with patch("services.price_analytics.get_supabase") as mock:
            mock.return_value = MockSupabaseClient(MockQueryBuilder(data))
            result = get_longitudinal_winners()
        assert result == []

    def test_price_trends_returns_empty_when_no_data(self):
        from services.price_service import get_price_trends

        with patch("services.price_analytics.get_supabase") as mock:
            mock.return_value = MockSupabaseClient(MockQueryBuilder([]))
            result = get_price_trends("leite", days=90)
        assert result == []

    def test_price_trends_computes_avg_min_max(self):
        from services.price_service import get_price_trends

        data = [
            {"store_name": "Assai", "normalized": {"price_per_kg": 10.0}, "collected_at": "2026-06-01"},
            {"store_name": "Atacadao", "normalized": {"price_per_kg": 12.0}, "collected_at": "2026-06-01"},
            {"store_name": "Assai", "normalized": {"price_per_kg": 11.0}, "collected_at": "2026-06-02"},
            {"store_name": "Atacadao", "normalized": {"price_per_kg": 9.0}, "collected_at": "2026-06-02"},
        ]
        with patch("services.price_analytics.get_supabase") as mock:
            mock.return_value = MockSupabaseClient(MockQueryBuilder(data))
            result = get_price_trends("leite", days=90)
        assert len(result) == 2
        assert result[0]["date"] == "2026-06-01"
        assert result[0]["avg_ppk"] == 11.0
        assert result[0]["min_ppk"] == 10.0
        assert result[0]["max_ppk"] == 12.0
        assert result[0]["store_count"] == 2

    def test_cross_ingredient_ranking_returns_empty_when_no_data(self):
        from services.price_service import get_cross_ingredient_ranking

        with patch("services.price_analytics.get_supabase") as mock:
            mock.return_value = MockSupabaseClient(MockQueryBuilder([]))
            result = get_cross_ingredient_ranking(days=90)
        assert result == []

    def test_cross_ingredient_ranking_counts_top1_and_top3(self):
        from services.price_service import get_cross_ingredient_ranking

        data = [
            {
                "ingredient_id": "leite",
                "store_name": "Assai",
                "normalized": {"price_per_kg": 10.0},
                "collected_at": "2026-06-01",
            },
            {
                "ingredient_id": "leite",
                "store_name": "Atacadao",
                "normalized": {"price_per_kg": 12.0},
                "collected_at": "2026-06-01",
            },
            {
                "ingredient_id": "choco",
                "store_name": "Assai",
                "normalized": {"price_per_kg": 20.0},
                "collected_at": "2026-06-01",
            },
            {
                "ingredient_id": "choco",
                "store_name": "Atacadao",
                "normalized": {"price_per_kg": 18.0},
                "collected_at": "2026-06-01",
            },
        ]
        with patch("services.price_analytics.get_supabase") as mock:
            mock.return_value = MockSupabaseClient(MockQueryBuilder(data))
            result = get_cross_ingredient_ranking(days=90)
        assert len(result) == 2
        scores = {r["store_name"]: r for r in result}
        assert scores["Assai"]["top1_count"] == 1  # leite
        assert scores["Assai"]["top3_count"] == 2  # leite + choco
        assert scores["Atacadao"]["top1_count"] == 1  # choco
        assert scores["Atacadao"]["top3_count"] == 2  # leite + choco
