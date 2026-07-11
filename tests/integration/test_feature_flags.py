#!/usr/bin/env python3
"""
Testes de integração para Feature Flags (DB-backed).
Valida que flags podem ser alteradas e recuperadas corretamente.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from tests.conftest import _has_real_db as _has_db_creds


pytestmark = pytest.mark.skipif(
    not _has_db_creds(),
    reason="SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set",
)

from services import config_db


class TestFeatureFlags:
    """Valida o ciclo de vida de Feature Flags no banco de dados."""

    TEST_FLAG = "_test_integration_flag"

    def test_upsert_and_get_flag(self):
        """Upsert de flag deve ser refletido no get."""
        # Set to True
        config_db.upsert_feature_flag(self.TEST_FLAG, True, "Test flag enabled")
        assert config_db.get_feature_flag(self.TEST_FLAG) is True

        # Set to False
        config_db.upsert_feature_flag(self.TEST_FLAG, False, "Test flag disabled")
        assert config_db.get_feature_flag(self.TEST_FLAG) is False

    def test_get_non_existent_flag_returns_default(self):
        """Flag inexistente deve retornar o valor default fornecido."""
        res = config_db.get_feature_flag("non_existent_flag_12345", default=True)
        assert res is True

        res = config_db.get_feature_flag("non_existent_flag_12345", default=False)
        assert res is False

    def test_get_all_flags(self):
        """get_all_feature_flags deve retornar a lista completa."""
        config_db.upsert_feature_flag(self.TEST_FLAG, True, "Test all flags")
        flags = config_db.get_all_feature_flags()

        # Verify our test flag is in the list
        found = any(f["key"] == self.TEST_FLAG for f in flags)
        assert found, f"Flag {self.TEST_FLAG} not found in all_flags list"

    def test_flag_persistence(self):
        """Valida que a flag persiste após reload (simulado via service call)."""
        config_db.upsert_feature_flag(self.TEST_FLAG, True, "Persistence test")

        # Simulate a new session by just calling the function again
        assert config_db.get_feature_flag(self.TEST_FLAG) is True
