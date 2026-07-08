"""Tests for services/telegram_service.py — token missing must not raise."""

import os
from unittest.mock import patch

import pytest

from services.telegram_service import send_telegram_message


def test_send_message_returns_false_when_no_token():
    """Must NOT raise ValueError — return False instead."""
    with patch.dict(os.environ, {}, clear=True):
        result = send_telegram_message("123", "test")
        assert result is False


def test_send_message_returns_false_on_api_error():
    """Must return False on HTTP error, not raise."""
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake:token"}, clear=True):
        with patch("httpx.post") as mock_post:
            mock_post.side_effect = Exception("Connection error")
            result = send_telegram_message("123", "test")
            assert result is False


def test_send_message_success():
    """Must return True on 200 OK."""
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake:token"}, clear=True):
        with patch("httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            result = send_telegram_message("123", "test")
            assert result is True
