import pytest
from datetime import datetime, timedelta, UTC


def _assert_html(html, expected_class, expected_text=None):
    assert f'class="cd-badge {expected_class}"' in html
    if expected_text:
        assert expected_text in html


def test_freshness_badge_html_now():
    from dashboard.components.ui import _freshness_badge_html

    html = _freshness_badge_html(datetime.now(UTC))
    _assert_html(html, "success", "hoje")


def test_freshness_badge_html_1_day():
    from dashboard.components.ui import _freshness_badge_html

    ts = datetime.now(UTC) - timedelta(days=1)
    html = _freshness_badge_html(ts)
    _assert_html(html, "success", "1d")


def test_freshness_badge_html_7_days():
    from dashboard.components.ui import _freshness_badge_html

    ts = datetime.now(UTC) - timedelta(days=7)
    html = _freshness_badge_html(ts)
    _assert_html(html, "success", "7d")


def test_freshness_badge_html_8_days():
    from dashboard.components.ui import _freshness_badge_html

    ts = datetime.now(UTC) - timedelta(days=8)
    html = _freshness_badge_html(ts)
    _assert_html(html, "warning", "8d")


def test_freshness_badge_html_30_days():
    from dashboard.components.ui import _freshness_badge_html

    ts = datetime.now(UTC) - timedelta(days=30)
    html = _freshness_badge_html(ts)
    _assert_html(html, "warning", "30d")


def test_freshness_badge_html_31_days():
    from dashboard.components.ui import _freshness_badge_html

    ts = datetime.now(UTC) - timedelta(days=31)
    html = _freshness_badge_html(ts)
    _assert_html(html, "danger", "31d stale")


def test_freshness_badge_html_string_iso():
    from dashboard.components.ui import _freshness_badge_html

    ts_str = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    html = _freshness_badge_html(ts_str)
    _assert_html(html, "success")


def test_freshness_badge_html_string_invalid():
    from dashboard.components.ui import _freshness_badge_html

    html = _freshness_badge_html("not-a-date")
    _assert_html(html, "neutral", "n/d")


def test_freshness_badge_html_none():
    from dashboard.components.ui import _freshness_badge_html

    html = _freshness_badge_html(None)
    _assert_html(html, "neutral", "n/d")


def test_freshness_badge_html_naive_datetime():
    from dashboard.components.ui import _freshness_badge_html

    ts = datetime.now()
    html = _freshness_badge_html(ts)
    # naive datetime gets UTC tzinfo, so days could be 0 or 1 depending on time
    assert 'class="cd-badge' in html


def test_freshness_badge_html_custom_now():
    from dashboard.components.ui import _freshness_badge_html

    now = datetime(2026, 1, 15, tzinfo=UTC)
    ts = datetime(2026, 1, 10, tzinfo=UTC)  # 5 days ago
    html = _freshness_badge_html(ts, now=now)
    _assert_html(html, "success", "5d")


def test_freshness_badge_html_threshold_boundaries():
    """Test exact boundary conditions."""
    from dashboard.components.ui import _freshness_badge_html

    now = datetime(2026, 1, 15, tzinfo=UTC)

    # exactly 7 days -> success
    html = _freshness_badge_html(datetime(2026, 1, 8, tzinfo=UTC), now=now)
    _assert_html(html, "success", "7d")

    # exactly 8 days -> warning
    html = _freshness_badge_html(datetime(2026, 1, 7, tzinfo=UTC), now=now)
    _assert_html(html, "warning", "8d")

    # exactly 30 days -> warning
    html = _freshness_badge_html(datetime(2025, 12, 16, tzinfo=UTC), now=now)
    _assert_html(html, "warning", "30d")

    # exactly 31 days -> danger
    html = _freshness_badge_html(datetime(2025, 12, 15, tzinfo=UTC), now=now)
    _assert_html(html, "danger", "31d stale")


def test_freshness_badge_st_widget():
    """Ensure the widget function still works (smoke test)."""
    from dashboard.components.ui import freshness_badge

    freshness_badge(datetime.now(UTC))
    freshness_badge(None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
