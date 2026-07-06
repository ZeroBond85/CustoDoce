class TestAuthTotp:
    """Testes P0 para services/auth.py — verify_totp() e _totp_int()."""

    def test_totp_int_returns_int(self):
        from services.auth import _totp_int, generate_totp_secret

        secret = generate_totp_secret()
        code = _totp_int(secret, 12345678)
        assert isinstance(code, int)
        assert 0 <= code <= 999999

    def test_verify_totp_invalid_string(self):
        from services.auth import verify_totp

        assert verify_totp("SECRET", "") is False
        assert verify_totp("SECRET", "abc123") is False

    def test_verify_totp_wrong_code(self):
        from services.auth import verify_totp

        secret = "AAAAAAAAAAAAAAAA"
        assert verify_totp(secret, "000000") is False
