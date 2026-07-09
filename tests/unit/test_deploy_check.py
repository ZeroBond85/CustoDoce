"""Unit tests for scripts/deploy_check.py — validates each check function in isolation."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.auth import hash_password, verify_password
from services.rate_limiter import RateLimiter


class TestYamlConfigs:
    def test_yaml_files_exist(self):
        for path in ["config/ingredients.yaml", "config/stores.yaml", "config/features.yaml"]:
            assert Path(path).exists(), f"{path} nao encontrado"

    def test_yaml_files_parse(self):
        import yaml
        for path in ["config/ingredients.yaml", "config/stores.yaml", "config/features.yaml"]:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            assert data, f"{path} retornou vazio"


class TestFeaturesConfig:
    def test_features_loaded(self):
        from services.config import get as get_config
        assert get_config("features.telegram.enabled") is not None
        assert get_config("features.email.enabled") is not None
        assert get_config("features.alerts.price_variation_pct") is not None

    def test_features_have_values(self):
        from services.config import get as get_config
        assert isinstance(get_config("features.telegram.enabled"), bool)
        assert isinstance(get_config("features.email.enabled"), bool)


class TestAuth:
    def test_hash_and_verify(self):
        h = hash_password("unit_test")
        assert verify_password("unit_test", h), "hash/verify mismatch"

    def test_wrong_password_fails(self):
        h = hash_password("correct")
        assert not verify_password("wrong", h), "wrong password should fail"


class TestRateLimiter:
    def test_not_limited(self):
        rl = RateLimiter()
        assert rl.is_limited("new_key") is False

    def test_limited_after_many_attempts(self):
        rl = RateLimiter()
        key = "test_rate_key_123"
        for _ in range(5):
            rl.record_attempt(key)
        assert rl.is_limited(key)
        rl.clear_attempts(key)

    def test_not_limited_below_threshold(self):
        rl = RateLimiter()
        key = "test_rate_key_not_limited"
        for _ in range(4):
            rl.record_attempt(key)
        assert not rl.is_limited(key)
        rl.clear_attempts(key)


class TestDeployCheckScript:
    def test_script_file_exists(self):
        assert Path("scripts/deploy_check.py").exists()

    def test_script_is_valid_python(self):
        import py_compile
        py_compile.compile("scripts/deploy_check.py", doraise=True)

    def test_script_has_required_keywords(self):
        with open("scripts/deploy_check.py", encoding="utf-8") as f:
            content = f.read()
        assert "def test_supabase" in content
        assert "def test_telegram" in content
        assert "def test_smtp" in content
        assert "if __name__ == \"__main__\"" in content


class TestTelegramCheck:
    def test_skip_when_no_token(self):
        from scripts.deploy_check import test_telegram
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)
        test_telegram()  # should not raise

    @patch("httpx.post")
    def test_send_with_token(self, mock_post):
        mock_post.return_value.status_code = 200
        os.environ["TELEGRAM_BOT_TOKEN"] = "fake:token"
        os.environ["TELEGRAM_CHAT_ID"] = "123"
        try:
            from scripts.deploy_check import test_telegram
            test_telegram()
        finally:
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            os.environ.pop("TELEGRAM_CHAT_ID", None)

    @patch("httpx.post")
    def test_telegram_http_error(self, mock_post):
        mock_post.return_value.status_code = 401
        os.environ["TELEGRAM_BOT_TOKEN"] = "fake:token"
        os.environ["TELEGRAM_CHAT_ID"] = "123"
        with pytest.raises(AssertionError):
            from scripts.deploy_check import test_telegram
            test_telegram()
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)


class TestSMTPCheck:
    @patch("smtplib.SMTP")
    def test_smtp_with_env(self, mock_smtp):
        os.environ["SMTP_HOST"] = "smtp.test.com"
        os.environ["SMTP_USER"] = "user"
        os.environ["SMTP_PASSWORD"] = "pass"
        os.environ["SMTP_FROM"] = "from@test.com"
        os.environ["ALERT_EMAIL_TO"] = "to@test.com"
        os.environ["SMTP_PORT"] = "587"
        try:
            from scripts.deploy_check import test_smtp
            test_smtp()

            mock_smtp.assert_called_once()
            instance = mock_smtp.return_value.__enter__.return_value
            instance.send_message.assert_called_once()
        finally:
            for k in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "ALERT_EMAIL_TO", "SMTP_PORT"]:
                os.environ.pop(k, None)

    def test_smtp_missing_creds_raises(self):
        os.environ.pop("SMTP_HOST", None)
        os.environ.pop("SMTP_USER", None)
        with pytest.raises(ValueError, match="SMTP_USER"):
            from scripts.deploy_check import test_smtp
            test_smtp()
