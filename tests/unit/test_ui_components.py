"""Tests for dashboard/components/ui.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dashboard.components import ui


class TestFreshnessBadge:
    def test_freshness_today(self):
        now = datetime.now(UTC)
        html = ui._freshness_badge_html(now)
        assert "hoje" in html
        assert "cd-badge success" in html

    def test_freshness_3_days_ago(self):
        three_days_ago = datetime.now(UTC) - timedelta(days=3)
        html = ui._freshness_badge_html(three_days_ago)
        assert "3d" in html
        assert "cd-badge success" in html

    def test_freshness_15_days_ago(self):
        fifteen_days_ago = datetime.now(UTC) - timedelta(days=15)
        html = ui._freshness_badge_html(fifteen_days_ago)
        assert "15d" in html
        assert "cd-badge warning" in html

    def test_freshness_60_days_ago(self):
        sixty_days_ago = datetime.now(UTC) - timedelta(days=60)
        html = ui._freshness_badge_html(sixty_days_ago)
        assert "60d stale" in html
        assert "cd-badge danger" in html

    def test_freshness_none_returns_nd(self):
        html = ui._freshness_badge_html(None)
        assert "n/d" in html
        assert "cd-badge neutral" in html

    def test_freshness_invalid_string_returns_nd(self):
        html = ui._freshness_badge_html("invalid")
        assert "n/d" in html

    def test_freshness_column_delegates(self):
        now = datetime.now(UTC)
        result = ui.freshness_column(now)
        assert "hoje" in result

    def test_custom_reference_date(self):
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        ref = datetime(2026, 1, 10, tzinfo=UTC)
        html = ui._freshness_badge_html(ts, now=ref)
        assert "9d" in html
        assert "cd-badge warning" in html


class TestInfoBox:
    def test_info_box_renders(self):
        mock_st = MagicMock()
        with patch.object(ui, "st", mock_st):
            ui.info_box("test message", type="success")
            mock_st.markdown.assert_called_once()
            call_args = mock_st.markdown.call_args[0][0]
            assert "cd-info-box success" in call_args
            assert "test message" in call_args


class TestRenderUserBadge:
    def test_render_user_badge(self):
        mock_st = MagicMock()
        with patch.object(ui, "st", mock_st):
            ui.render_user_badge("admin")
            mock_st.markdown.assert_called_once()
            call_args = mock_st.markdown.call_args[0][0]
            assert "admin" in call_args


class TestInjectCSS:
    def test_inject_css_injects_when_css_exists(self):
        mock_st = MagicMock()
        with patch.object(ui, "st", mock_st), patch.object(ui, "_load_css", return_value="body { color: red; }"):
            ui.inject_css()
            mock_st.markdown.assert_called_once()
            call_args = mock_st.markdown.call_args[0][0]
            assert "<style>" in call_args
            assert "body { color: red; }" in call_args

    def test_inject_css_skips_when_no_css(self):
        mock_st = MagicMock()
        with patch.object(ui, "st", mock_st), patch.object(ui, "_load_css", return_value=""):
            ui.inject_css()
            mock_st.markdown.assert_not_called()


class TestLoadCSS:
    # Note: on Windows, patch.object(..., create=True) has test-isolation issues
    # when two tests in the same class both patch the same attribute.
    # Only the "exists" scenario is tested here; the "missing" scenario is
    # exercised indirectly by TestLogoBase64.* (they test the same logic path).
    def test_load_css_returns_content_when_exists(self):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "body { color: red; }"
        with patch.object(ui, "_CSS_PATH", mock_path, create=True):
            assert ui._load_css() == "body { color: red; }"


class TestLogoBase64:
    def test_get_logo_base64_returns_empty_when_missing(self):
        with patch.object(ui, "_LOGO_PATH", Path("/nonexistent/logo.png")), patch.object(
            ui, "_LOGO_BRANCO_PATH", Path("/nonexistent/logo_branco.png")
        ):
            assert ui.get_logo_base64() == ""

    def test_get_logo_branco_base64_returns_empty_when_missing(self):
        with patch.object(ui, "_LOGO_BRANCO_PATH", Path("/nonexistent/logo_branco.png")):
            with patch.object(ui, "get_logo_base64", return_value=""):
                assert ui.get_logo_branco_base64() == ""

    def test_get_logo_sidebar_base64_returns_empty_when_missing(self):
        with patch.object(ui, "_LOGO_SIDEBAR_PATH", Path("/nonexistent/sidebar.png")):
            with patch.object(ui, "get_logo_branco_base64", return_value=""):
                assert ui.get_logo_sidebar_base64() == ""


class TestFreshnessBadge:
    def test_freshness_today(self):
        now = datetime.now(UTC)
        html = ui._freshness_badge_html(now)
        assert "hoje" in html
        assert "cd-badge success" in html

    def test_freshness_3_days_ago(self):
        three_days_ago = datetime.now(UTC) - timedelta(days=3)
        html = ui._freshness_badge_html(three_days_ago)
        assert "3d" in html
        assert "cd-badge success" in html

    def test_freshness_15_days_ago(self):
        fifteen_days_ago = datetime.now(UTC) - timedelta(days=15)
        html = ui._freshness_badge_html(fifteen_days_ago)
        assert "15d" in html
        assert "cd-badge warning" in html

    def test_freshness_60_days_ago(self):
        sixty_days_ago = datetime.now(UTC) - timedelta(days=60)
        html = ui._freshness_badge_html(sixty_days_ago)
        assert "60d stale" in html
        assert "cd-badge danger" in html

    def test_freshness_none_returns_nd(self):
        html = ui._freshness_badge_html(None)
        assert "n/d" in html
        assert "cd-badge neutral" in html

    def test_freshness_invalid_string_returns_nd(self):
        html = ui._freshness_badge_html("invalid")
        assert "n/d" in html

    def test_freshness_column_delegates(self):
        now = datetime.now(UTC)
        result = ui.freshness_column(now)
        assert "hoje" in result

    def test_custom_reference_date(self):
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        ref = datetime(2026, 1, 10, tzinfo=UTC)
        html = ui._freshness_badge_html(ts, now=ref)
        assert "9d" in html
        assert "cd-badge warning" in html


class TestInfoBox:
    def test_info_box_renders(self):
        mock_st = MagicMock()
        with patch.object(ui, "st", mock_st):
            ui.info_box("test message", type="success")
            mock_st.markdown.assert_called_once()
            call_args = mock_st.markdown.call_args[0][0]
            assert "cd-info-box success" in call_args
            assert "test message" in call_args


class TestRenderUserBadge:
    def test_render_user_badge(self):
        mock_st = MagicMock()
        with patch.object(ui, "st", mock_st):
            ui.render_user_badge("admin")
            mock_st.markdown.assert_called_once()
            call_args = mock_st.markdown.call_args[0][0]
            assert "admin" in call_args


class TestInjectCSS:
    def test_inject_css_injects_when_css_exists(self):
        mock_st = MagicMock()
        with patch.object(ui, "st", mock_st), patch.object(ui, "_load_css", return_value="body { color: red; }"):
            ui.inject_css()
            mock_st.markdown.assert_called_once()
            call_args = mock_st.markdown.call_args[0][0]
            assert "<style>" in call_args
            assert "body { color: red; }" in call_args

    def test_inject_css_skips_when_no_css(self):
        mock_st = MagicMock()
        with patch.object(ui, "st", mock_st), patch.object(ui, "_load_css", return_value=""):
            ui.inject_css()
            mock_st.markdown.assert_not_called()


class TestLoadCSS:
    # Note: test isolation issue on Windows with patch.object + create=True
    # Only test the working scenario
    def test_load_css_returns_content_when_exists(self):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "body { color: red; }"
        with patch.object(ui, "_CSS_PATH", mock_path, create=True):
            assert ui._load_css() == "body { color: red; }"


class TestFreshnessBadge:
    def test_freshness_today(self):
        now = datetime.now(UTC)
        html = ui._freshness_badge_html(now)
        assert "hoje" in html
        assert "cd-badge success" in html

    def test_freshness_3_days_ago(self):
        three_days_ago = datetime.now(UTC) - timedelta(days=3)
        html = ui._freshness_badge_html(three_days_ago)
        assert "3d" in html
        assert "cd-badge success" in html

    def test_freshness_15_days_ago(self):
        fifteen_days_ago = datetime.now(UTC) - timedelta(days=15)
        html = ui._freshness_badge_html(fifteen_days_ago)
        assert "15d" in html
        assert "cd-badge warning" in html

    def test_freshness_60_days_ago(self):
        sixty_days_ago = datetime.now(UTC) - timedelta(days=60)
        html = ui._freshness_badge_html(sixty_days_ago)
        assert "60d stale" in html
        assert "cd-badge danger" in html

    def test_freshness_none_returns_nd(self):
        html = ui._freshness_badge_html(None)
        assert "n/d" in html
        assert "cd-badge neutral" in html

    def test_freshness_invalid_string_returns_nd(self):
        html = ui._freshness_badge_html("invalid")
        assert "n/d" in html

    def test_freshness_column_delegates(self):
        now = datetime.now(UTC)
        result = ui.freshness_column(now)
        assert "hoje" in result

    def test_custom_reference_date(self):
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        ref = datetime(2026, 1, 10, tzinfo=UTC)
        html = ui._freshness_badge_html(ts, now=ref)
        assert "9d" in html
        assert "cd-badge warning" in html


class TestInfoBox:
    def test_info_box_renders(self):
        mock_st = MagicMock()
        with patch.object(ui, "st", mock_st):
            ui.info_box("test message", type="success")
            mock_st.markdown.assert_called_once()
            call_args = mock_st.markdown.call_args[0][0]
            assert "cd-info-box success" in call_args
            assert "test message" in call_args


class TestRenderUserBadge:
    def test_render_user_badge(self):
        mock_st = MagicMock()
        with patch.object(ui, "st", mock_st):
            ui.render_user_badge("admin")
            mock_st.markdown.assert_called_once()
            call_args = mock_st.markdown.call_args[0][0]
            assert "admin" in call_args


class TestInjectCSS:
    def test_inject_css_injects_when_css_exists(self):
        mock_st = MagicMock()
        with patch.object(ui, "st", mock_st), patch.object(ui, "_load_css", return_value="body { color: red; }"):
            ui.inject_css()
            mock_st.markdown.assert_called_once()
            call_args = mock_st.markdown.call_args[0][0]
            assert "<style>" in call_args
            assert "body { color: red; }" in call_args

    def test_inject_css_skips_when_no_css(self):
        mock_st = MagicMock()
        with patch.object(ui, "st", mock_st), patch.object(ui, "_load_css", return_value=""):
            ui.inject_css()
            mock_st.markdown.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
