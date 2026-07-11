"""Tests for dashboard/pages/ pure functions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from dashboard.pages import insights, alertas, capacity_planning


class TestInsights:
    def test_safe_ppk_with_valid_dict(self):
        r = {"normalized": {"price_per_kg": 26.58}}
        assert insights._safe_ppk(r) == 26.58

    def test_safe_ppk_with_none_normalized(self):
        r = {"normalized": None}
        assert insights._safe_ppk(r) == 0.0

    def test_safe_ppk_with_missing_normalized(self):
        r = {}
        assert insights._safe_ppk(r) == 0.0

    def test_safe_ppk_with_invalid_price(self):
        r = {"normalized": {"price_per_kg": "abc"}}
        assert insights._safe_ppk(r) == 0.0


class TestAlertasPagination:
    def _mock_st_columns(self, mock_st, n=5):
        cols = [MagicMock() for _ in range(n)]
        mock_st.columns.return_value = cols
        return cols

    def test_fallback_pagination_first_page(self):
        mock_st = MagicMock()
        mock_st.query_params = {"alerts_page": "1"}
        self._mock_st_columns(mock_st)
        with patch("dashboard.pages.alertas.st", mock_st):
            assert alertas._fallback_pagination(total_pages=5) == 1

    def test_fallback_pagination_middle_page(self):
        mock_st = MagicMock()
        mock_st.query_params = {"alerts_page": "3"}
        self._mock_st_columns(mock_st)
        with patch("dashboard.pages.alertas.st", mock_st):
            assert alertas._fallback_pagination(total_pages=5) == 3

    def test_fallback_pagination_invalid_defaults_to_one(self):
        mock_st = MagicMock()
        mock_st.query_params = {"alerts_page": "xyz"}
        self._mock_st_columns(mock_st)
        with patch("dashboard.pages.alertas.st", mock_st):
            assert alertas._fallback_pagination(total_pages=5) == 1

    def test_fallback_pagination_clamped_to_max(self):
        mock_st = MagicMock()
        mock_st.query_params = {"alerts_page": "99"}
        self._mock_st_columns(mock_st)
        with patch("dashboard.pages.alertas.st", mock_st):
            assert alertas._fallback_pagination(total_pages=5) == 5


class TestAlertasContactOptions:
    def test_contact_options_returns_targets(self):
        with patch("dashboard.pages.alertas.cached_get_active_recipients", return_value=[
            {"target": "a@example.com", "channel": "email"},
            {"target": "b@example.com", "channel": "email"},
        ]):
            opts = alertas._contact_options("email")
            assert set(opts) == {"a@example.com", "b@example.com"}

    def test_contact_options_empty_when_no_recipients(self):
        with patch("dashboard.pages.alertas.cached_get_active_recipients", return_value=[]):
            assert alertas._contact_options("email") == []


class TestLojaPendentesPendingTab:
    def test_render_pending_tab_builds_dataframe(self):
        """Test that _render_pending_tab builds DataFrame with expected columns."""
        class MockEntry:
            def __init__(self, id, name, tier, type_, city, source, match_score, status):
                self.id = id
                self.name = name
                self.tier = tier
                self.type = type_
                self.city = city
                self.source = source
                self.match_score = match_score
                self.status = status

        pending = [
            MockEntry("abc12345", "Loja A", 1, "atacadista", "Santos", "auto", 0.95, "pending"),
            MockEntry("def67890", "Loja B", 2, "ecommerce", "SP", "api", 0.80, "pending"),
        ]

        import pandas as pd
        df = pd.DataFrame([
            {
                "ID": e.id[:8] + "...",
                "Nome": e.name,
                "Tier": e.tier,
                "Tipo": e.type,
                "Cidade": e.city or "-",
                "Origem": e.source,
                "Match": f"{e.match_score:.0%}" if e.match_score else "-",
                "Status": e.status,
            }
            for e in pending
        ])
        assert list(df.columns) == ["ID", "Nome", "Tier", "Tipo", "Cidade", "Origem", "Match", "Status"]
        assert len(df) == 2


class TestCapacityPlanning:
    def test_disk_usage_mb_returns_zero_on_error(self):
        with patch("dashboard.pages.capacity_planning.get_supabase", side_effect=Exception("fail")):
            mb, count = capacity_planning._get_disk_usage_mb()
            assert mb == 0.0
            assert count == 0

    def test_actions_minutes_returns_zero_on_error(self):
        with patch("dashboard.pages.capacity_planning.get_supabase", side_effect=Exception("fail")):
            minutes, count = capacity_planning._get_actions_minutes_used()
            assert minutes == 0.0
            assert count == 0

    def test_smtp_quota_returns_zero_on_error(self):
        with patch("dashboard.pages.capacity_planning.get_supabase", side_effect=Exception("fail")):
            count = capacity_planning._get_smtp_quota_used()
            assert count == 0
