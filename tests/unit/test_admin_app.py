import importlib
import os
from unittest.mock import patch


def test_admin_password_none_when_missing():
    """Verifica que ADMIN_PASSWORD fica None quando env var nao definida."""
    with patch.dict(os.environ, {}, clear=True):
        import admin.app as app

        importlib.reload(app)

        assert app.ADMIN_PASSWORD is None


def test_admin_password_reads_from_env():
    """Verifica que ADMIN_PASSWORD le do environment."""
    with patch.dict(os.environ, {"ADMIN_PASSWORD": "my-test-pw"}, clear=True):
        import admin.app as app

        importlib.reload(app)

        assert app.ADMIN_PASSWORD == "my-test-pw"
