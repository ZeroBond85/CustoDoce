import os
from unittest.mock import patch

import pytest

from services.email_service import _get_smtp_config, send_email


@pytest.fixture
def mock_smtp():
    with patch("smtplib.SMTP") as mock_smtp:
        instance = mock_smtp.return_value
        instance.login.return_value = None
        instance.send_message.return_value = None
        instance.quit.return_value = None
        yield instance


@pytest.mark.parametrize(
    "env_vars, expected_host, expected_port",
    [
        ({}, "smtp.gmail.com", 587),
        ({"SMTP_HOST": "smtp.test.com", "SMTP_PORT": "465"}, "smtp.test.com", 465),
        ({"SMTP_HOST": "smtp.custom.com"}, "smtp.custom.com", 587),
    ],
)
def test_get_smtp_config(env_vars, expected_host, expected_port):
    with patch.dict(os.environ, env_vars, clear=True):
        host, port, _, _, _ = _get_smtp_config()
        assert host == expected_host
        assert port == expected_port


def test_send_email_success(mock_smtp):
    with patch.dict(
        os.environ, {"SMTP_USER": "user@test.com", "SMTP_PASSWORD": "password", "SMTP_FROM": "from@test.com"}
    ):
        send_email("to@test.com", "Subject", "Body")
        mock_smtp.login.assert_called()
        mock_smtp.send_message.assert_called()
        mock_smtp.quit.assert_called()


def test_send_email_no_creds():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="SMTP credentials not configured"):
            send_email("to@test.com", "Subject", "Body")


@pytest.mark.parametrize(
    "to_email, expected_raise",
    [
        ("valid@test.com", False),
        ("", True),
        (None, True),
    ],
)
def test_send_email_to_validation(mock_smtp, to_email, expected_raise):
    with patch.dict(
        os.environ,
        {
            "SMTP_USER": "user@test.com",
            "SMTP_PASSWORD": "password",
        },
    ):
        if expected_raise:
            with pytest.raises(ValueError):
                send_email(to_email, "Subject", "Body")
        else:
            send_email(to_email, "Subject", "Body")


def test_send_email_connection_error(mock_smtp):
    mock_smtp.login.side_effect = Exception("Connection failed")
    with patch.dict(
        os.environ,
        {
            "SMTP_USER": "user@test.com",
            "SMTP_PASSWORD": "password",
        },
    ):
        with pytest.raises(Exception, match="Connection failed"):
            send_email("to@test.com", "Subject", "Body")
