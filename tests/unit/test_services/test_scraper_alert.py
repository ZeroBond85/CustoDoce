"""Unit tests for services/scraper_alert.py (notificações de saúde de scraper)."""

from __future__ import annotations

from unittest.mock import patch

from services import scraper_alert


def test_notify_scraper_disabled_sends_alert():
    with patch.object(scraper_alert, "get_feature", return_value=True), patch.object(
        scraper_alert, "_send_alert"
    ) as mock_send:
        mock_send.return_value = True
        ok = scraper_alert.notify_scraper_disabled("base_flyer", "timeout", 3)
    assert ok is True
    sent = mock_send.call_args[0][0]
    assert "base_flyer" in sent
    assert "timeout" in sent
    assert "3" in sent


def test_notify_health_critical_sends_alert():
    with patch.object(scraper_alert, "get_feature", return_value=True), patch.object(
        scraper_alert, "_send_alert"
    ) as mock_send:
        mock_send.return_value = True
        ok = scraper_alert.notify_health_critical("vtex_api", 12)
    assert ok is True
    assert "vtex_api" in mock_send.call_args[0][0]
    assert "12" in mock_send.call_args[0][0]


def test_notify_scraper_recovered_sends_alert():
    with patch.object(scraper_alert, "get_feature", return_value=True), patch.object(
        scraper_alert, "_send_alert"
    ) as mock_send:
        mock_send.return_value = True
        ok = scraper_alert.notify_scraper_recovered("base_flyer")
    assert ok is True
    assert "base_flyer" in mock_send.call_args[0][0]


def test_notify_disabled_respects_feature_gate():
    with patch.object(scraper_alert, "get_feature", return_value=False), patch.object(
        scraper_alert, "_send_alert"
    ) as mock_send:
        ok = scraper_alert.notify_scraper_disabled("base_flyer", "timeout", 3)
    assert ok is False
    mock_send.assert_not_called()


def test_send_alert_false_without_chat_id(monkeypatch):
    monkeypatch.delenv("SCRAPER_ALERT_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("ALERT_CHAT_ID", raising=False)
    monkeypatch.setattr(scraper_alert, "_DEFAULT_CHAT_ID", "")
    assert scraper_alert._send_alert(" qualquer ") is False
