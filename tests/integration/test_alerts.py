#!/usr/bin/env python3
"""
Testes de integração para Regras de Alerta.
Valida que a configuração de regras no DB é recuperada corretamente.
"""

import os
import sys
from pathlib import Path
import pytest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _has_db_creds():
    url = os.environ.get("SUPABASE_URL", "")
    pwd = os.environ.get("SUPABASE_DB_PASSWORD", "")
    return bool(url and pwd)


pytestmark = pytest.mark.skipif(
    not _has_db_creds(),
    reason="SUPABASE_URL / SUPABASE_DB_PASSWORD not set",
)

from services import config_db


class TestAlertRules:
    """Valida a gestão de regras de alerta no banco de dados."""

    def test_upsert_and_get_alert_rule(self):
        """Upsert de regra de alerta deve ser recuperável."""
        rule_id = str(uuid.uuid4())
        rule_data = {
            "id": rule_id,
            "name": "Test Alert Rule",
            "channel": "email",
            "trigger": "price_drop",
            "condition": {"threshold": 10.0},
            "enabled": True,
            "description": "Test rule description",
        }

        config_db.upsert_alert_rule(rule_data)

        # Debug: check if upsert worked
        res = config_db.get_all_alert_rules(include_disabled=True)
        assert any(r["id"] == rule_id for r in res), f"Rule {rule_id} not found even in all rules"

        # Get enabled rules
        enabled_rules = config_db.get_enabled_alert_rules()
        assert any(r["id"] == rule_id for r in enabled_rules), f"Rule {rule_id} not found in enabled rules"

        # Disable and check
        rule_data["enabled"] = False
        config_db.upsert_alert_rule(rule_data)

        enabled_rules = config_db.get_enabled_alert_rules()
        assert not any(r["id"] == rule_id for r in enabled_rules)

    def test_delete_alert_rule(self):
        """Regra deletada não deve mais aparecer."""
        rule_id = str(uuid.uuid4())
        rule_data = {
            "id": rule_id,
            "name": "Delete Test Rule",
            "channel": "email",
            "trigger": "price_drop",
            "condition": {},
            "enabled": True,
        }
        config_db.upsert_alert_rule(rule_data)

        config_db.delete_alert_rule(rule_id)

        all_rules = config_db.get_all_alert_rules()
        assert not any(r["id"] == rule_id for r in all_rules)
