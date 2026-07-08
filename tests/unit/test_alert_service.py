"""Tests for services/alert_service.py — notification errors must not propagate."""

from unittest.mock import MagicMock, patch

from services.alert_service import process_proactive_alerts


def _make_mock_client(has_rules=True, has_recipients=True, has_failures=False):
    """Build a mock supabase client with chainable query builders."""
    rules_data = [
        {"id": "r1", "trigger": "price_drop", "channel": "telegram", "enabled": True},
        {"id": "r2", "trigger": "scrape_failure", "channel": "email", "enabled": True},
    ] if has_rules else []

    latest_data = [
        {"ingredient_id": "Leite Condensado", "store_name": "Loja A", "price_per_kg": 8.50}
    ] if has_rules else []

    history_data = [
        {"normalized": {"price_per_kg": 12.0}},
        {"normalized": {"price_per_kg": 11.5}},
    ]

    failures_data = [
        {"store_name": "Loja B", "errors": "Timeout"}
    ] if has_failures else []

    recipients_data = [
        {"target": "@user", "channel": "telegram", "active": True},
        {"target": "email@test.com", "channel": "email", "active": True},
    ] if has_recipients else []

    def chain(*_args, **_kwargs):
        return qb

    qb = MagicMock()
    qb.select.return_value = qb
    qb.eq.return_value = qb
    qb.order.return_value = qb
    qb.limit.return_value = qb
    qb.gte.return_value = qb
    qb.execute.side_effect = [
        MagicMock(data=rules_data),
        MagicMock(data=latest_data),
        MagicMock(data=history_data),
        MagicMock(data=recipients_data),
        MagicMock(data=failures_data),
        MagicMock(data=recipients_data),
    ]

    client = MagicMock()
    client.table.return_value = qb
    return client


class TestProcessProactiveAlerts:
    @patch("services.alert_service.get_supabase")
    def test_no_rules_returns_early(self, mock_get_supabase):
        client = _make_mock_client(has_rules=False)
        mock_get_supabase.return_value = client
        process_proactive_alerts()

    @patch("services.alert_service.get_supabase")
    @patch("services.alert_service.send_telegram_message")
    def test_telegram_error_caught_as_warning(self, mock_send_tg, mock_get_supabase):
        client = _make_mock_client()
        mock_get_supabase.return_value = client
        mock_send_tg.side_effect = Exception("TELEGRAM_TOKEN must be set")
        process_proactive_alerts()

    @patch("services.alert_service.get_supabase")
    @patch("services.alert_service.send_email_notification")
    def test_email_error_caught_as_warning(self, mock_send_email, mock_get_supabase):
        client = _make_mock_client(has_rules=True, has_recipients=True, has_failures=True)
        mock_get_supabase.return_value = client
        mock_send_email.side_effect = Exception("SMTP not configured")
        process_proactive_alerts()

    @patch("services.alert_service.get_supabase")
    @patch("services.alert_service.send_telegram_message")
    @patch("services.alert_service.send_email_notification")
    def test_all_notifications_succeed(self, mock_send_email, mock_send_tg, mock_get_supabase):
        client = _make_mock_client(has_rules=True, has_recipients=True, has_failures=True)
        mock_get_supabase.return_value = client
        process_proactive_alerts()
