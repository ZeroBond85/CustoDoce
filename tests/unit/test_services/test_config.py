from unittest.mock import patch

from tests.unit.test_services.conftest import MockQueryBuilder, MockQueryResult, MockSupabaseClient, make_mocks


class TestConfigDb:
    """Testes P0 para services/config_db.py — CRUD com mocks do Supabase."""

    @classmethod
    def setup_class(cls):
        import importlib
        import sys

        # test_dashboard_full.py sets sys.modules["services.config_db"] = MagicMock
        # which breaks real imports. Force re-import the real module.
        if "services.config_db" in sys.modules:
            del sys.modules["services.config_db"]
        import services.config_db as _real

        importlib.reload(_real)

    SAMPLE_INGREDIENTS = [
        {"id": "1", "canonical_name": "Leite Condensado Integral", "active": True},
        {"id": "2", "canonical_name": "Creme de Leite", "active": True},
    ]
    SAMPLE_STORES = [
        {"id": "s1", "name": "Assaí", "is_active": True, "tier": 1, "priority": 1, "type": "atacado"},
        {"id": "s2", "name": "Extra", "is_active": False, "tier": 2, "priority": 5, "type": "supermercado"},
    ]
    SAMPLE_SCHEDULES = [
        {"id": "sch1", "name": "Coleta Diaria", "enabled": True, "cron": "0 12 * * *"},
    ]
    SAMPLE_RECIPIENTS = [
        {"id": "r1", "name": "Admin", "channel": "email", "active": True},
    ]
    SAMPLE_FLAGS = [
        {"key": "telegram_enabled", "enabled": True, "description": "Enable Telegram"},
    ]

    # ── INGREDIENTS ──

    @patch("services.config_db.get_supabase")
    def test_get_active_ingredients(self, mock_get_supabase):
        from services.config_db import get_active_ingredients

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder(self.SAMPLE_INGREDIENTS))
        result = get_active_ingredients()
        assert len(result) == 2
        assert result[0]["canonical_name"] == "Leite Condensado Integral"

    @patch("services.config_db.get_supabase")
    def test_get_all_ingredients_includes_inactive(self, mock_get_supabase):
        from services.config_db import get_all_ingredients

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder(self.SAMPLE_INGREDIENTS))
        result = get_all_ingredients(include_inactive=True)
        assert len(result) == 2

    @patch("services.config_db.get_supabase")
    def test_get_ingredient_by_id_found(self, mock_get_supabase):
        from services.config_db import get_ingredient_by_id

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([self.SAMPLE_INGREDIENTS[0]]))
        result = get_ingredient_by_id("1")
        assert result is not None
        assert result["canonical_name"] == "Leite Condensado Integral"

    @patch("services.config_db.get_supabase")
    def test_get_ingredient_by_id_not_found(self, mock_get_supabase):
        from services.config_db import get_ingredient_by_id

        qb = MockQueryBuilder([])
        qb.single = lambda: qb
        qb.execute = lambda: MockQueryResult(None)
        mock_get_supabase.return_value = MockSupabaseClient(qb)
        result = get_ingredient_by_id("999")
        assert result is None

    @patch("services.config_db.get_service_client")
    def test_upsert_ingredient(self, mock_get_client):
        from services.config_db import upsert_ingredient

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client
        upsert_ingredient({"canonical_name": "Test", "active": True})
        assert qb._captured_upsert is not None
        assert qb._captured_upsert["canonical_name"] == "Test"
        assert "updated_at" in qb._captured_upsert

    @patch("services.config_db.get_service_client")
    def test_delete_ingredient(self, mock_get_client):
        from services.config_db import delete_ingredient

        qb = MockQueryBuilder([{"id": "123"}])
        mock_client = MockSupabaseClient(qb)
        mock_get_client.return_value = mock_client
        assert delete_ingredient("123") is True

    # ── STORES ──

    @patch("services.config_db.get_supabase")
    def test_get_active_stores(self, mock_get_supabase):
        from services.config_db import get_active_stores

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([self.SAMPLE_STORES[0]]))
        result = get_active_stores()
        assert len(result) == 1
        assert result[0]["name"] == "Assaí"

    @patch("services.config_db.get_supabase")
    def test_get_active_stores_filtered_by_tier(self, mock_get_supabase):
        from services.config_db import get_active_stores

        mock = MockSupabaseClient(MockQueryBuilder([]))
        mock_get_supabase.return_value = mock
        get_active_stores(tier=1)
        assert mock.qb is not None

    @patch("services.config_db.get_supabase")
    def test_get_all_stores_include_inactive(self, mock_get_supabase):
        from services.config_db import get_all_stores

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder(self.SAMPLE_STORES))
        result = get_all_stores(include_inactive=True)
        assert len(result) == 2

    @patch("services.config_db.get_service_client")
    def test_upsert_store(self, mock_get_client):
        from services.config_db import upsert_store

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client
        upsert_store({"name": "Test Store", "tier": 1, "is_active": True})
        assert qb._captured_upsert is not None
        assert qb._captured_upsert["name"] == "Test Store"

    @patch("services.config_db.get_service_client")
    def test_delete_store(self, mock_get_client):
        from services.config_db import delete_store

        qb = MockQueryBuilder([{"id": "s1"}])
        mock_client = MockSupabaseClient(qb)
        mock_get_client.return_value = mock_client
        assert delete_store("s1") is True

    @patch("services.config_db.get_service_client")
    def test_upsert_scrape_frequency_uses_on_conflict_store_id(self, mock_get_client):
        """Regressao: upsert SEM on_conflict duplicava linhas (494 vs 70 stores).

        O plain upsert gera nova UUID a cada escrita -> 424 duplicatas. O
        on_conflict=store_id garante 1 linha por loja mesmo sem unique index.
        """
        from services.config_db import upsert_scrape_frequency

        qb = MockQueryBuilder([{"id": "f1", "store_id": "s1"}])
        mock_client = MockSupabaseClient(qb)
        mock_get_client.return_value = mock_client
        upsert_scrape_frequency({"store_id": "s1", "tier": 1, "enabled": True})
        assert qb._captured_on_conflict == "store_id"

    # ── SCHEDULES ──

    @patch("services.config_db.get_supabase")
    def test_get_enabled_schedules(self, mock_get_supabase):
        from services.config_db import get_enabled_schedules

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder(self.SAMPLE_SCHEDULES))
        result = get_enabled_schedules()
        assert len(result) == 1
        assert result[0]["name"] == "Coleta Diaria"

    @patch("services.config_db.get_service_client")
    def test_upsert_schedule(self, mock_get_client):
        from services.config_db import upsert_schedule

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client
        upsert_schedule({"name": "Novo Cron", "cron": "0 6 * * *"})
        assert qb._captured_upsert is not None
        assert qb._captured_upsert["name"] == "Novo Cron"

    @patch("services.config_db.get_service_client")
    def test_update_schedule_run(self, mock_get_client):
        from datetime import datetime

        from services.config_db import update_schedule_run

        mock_client, _, _ = make_mocks()
        mock_get_client.return_value = mock_client
        now = datetime(2026, 6, 19)
        update_schedule_run("sch1", last_run=now)
        assert mock_client.qb is not None

    # ── RECIPIENTS ──

    @patch("services.config_db.get_supabase")
    def test_get_active_recipients(self, mock_get_supabase):
        from services.config_db import get_active_recipients

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder(self.SAMPLE_RECIPIENTS))
        result = get_active_recipients()
        assert len(result) == 1
        assert result[0]["channel"] == "email"

    @patch("services.config_db.get_supabase")
    def test_get_active_recipients_filtered(self, mock_get_supabase):
        from services.config_db import get_active_recipients

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder(self.SAMPLE_RECIPIENTS))
        result = get_active_recipients(channel="telegram")
        assert len(result) == 1  # mock returns data regardless of filter

    # ── FEATURE FLAGS ──

    @patch("services.config_db.get_supabase")
    def test_get_feature_flag_enabled(self, mock_get_supabase):
        from services.config_db import get_feature_flag

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([{"enabled": True}]))
        assert get_feature_flag("telegram_enabled") is True

    @patch("services.config_db.get_supabase")
    def test_get_feature_flag_disabled(self, mock_get_supabase):
        from services.config_db import get_feature_flag

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([{"enabled": False}]))
        assert get_feature_flag("telegram_enabled") is False

    @patch("services.config_db.get_supabase")
    def test_get_feature_flag_default(self, mock_get_supabase):
        from services.config_db import get_feature_flag

        qb = MockQueryBuilder([])
        qb.single = lambda: qb
        qb.execute = lambda: MockQueryResult(None)
        mock_get_supabase.return_value = MockSupabaseClient(qb)
        assert get_feature_flag("nonexistent", default=True) is True

    @patch("services.config_db.get_service_client")
    def test_upsert_feature_flag(self, mock_get_client):
        from services.config_db import upsert_feature_flag

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client
        upsert_feature_flag("test_flag", enabled=True, description="Test flag")
        assert qb._captured_upsert is not None
        assert qb._captured_upsert["key"] == "test_flag"
        assert qb._captured_upsert["enabled"] is True

    # ── SCRAPE FREQUENCIES ──

    @patch("services.config_db.get_supabase")
    def test_get_scrape_frequency(self, mock_get_supabase):
        from services.config_db import get_scrape_frequency

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([]))
        result = get_scrape_frequency()
        assert result == []

    @patch("services.config_db.get_service_client")
    def test_upsert_scrape_frequency(self, mock_get_client):
        from services.config_db import upsert_scrape_frequency

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client
        upsert_scrape_frequency({"store_id": "s1", "tier": 1, "enabled": True})
        assert qb._captured_upsert is not None

    @patch("services.config_db.get_service_client")
    def test_delete_scrape_frequency(self, mock_get_client):
        from services.config_db import delete_scrape_frequency

        qb = MockQueryBuilder([{"id": "f1"}])
        mock_client = MockSupabaseClient(qb)
        mock_get_client.return_value = mock_client
        assert delete_scrape_frequency("f1") is True

    # ── ALERT RULES ──

    @patch("services.config_db.get_supabase")
    def test_get_enabled_alert_rules(self, mock_get_supabase):
        from services.config_db import get_enabled_alert_rules

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([]))
        result = get_enabled_alert_rules()
        assert result == []

    @patch("services.config_db.get_service_client")
    def test_upsert_alert_rule(self, mock_get_client):
        from services.config_db import upsert_alert_rule

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client
        upsert_alert_rule({"name": "Price Drop", "trigger": "price_drop", "enabled": True})
        assert qb._captured_upsert is not None
        assert qb._captured_upsert["name"] == "Price Drop"

    @patch("services.config_db.get_service_client")
    def test_delete_alert_rule(self, mock_get_client):
        from services.config_db import delete_alert_rule

        qb = MockQueryBuilder([{"id": "r1"}])
        mock_client = MockSupabaseClient(qb)
        mock_get_client.return_value = mock_client
        assert delete_alert_rule("r1") is True

    # ── STORE LOOKUPS ──

    @patch("services.config_db.get_supabase")
    def test_get_store_by_id(self, mock_get_supabase):
        from services.config_db import get_store_by_id

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([self.SAMPLE_STORES[0]]))
        result = get_store_by_id("s1")
        assert result is not None
        assert result["name"] == "Assaí"

    @patch("services.config_db.get_supabase")
    def test_get_store_by_name(self, mock_get_supabase):
        from services.config_db import get_store_by_name

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([self.SAMPLE_STORES[0]]))
        result = get_store_by_name("Assaí")
        assert result is not None
        assert result["name"] == "Assaí"

    @patch("services.config_db.get_supabase")
    def test_get_ingredient_by_name(self, mock_get_supabase):
        from services.config_db import get_ingredient_by_name

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder([self.SAMPLE_INGREDIENTS[0]]))
        result = get_ingredient_by_name("Leite Condensado Integral")
        assert result is not None

    # ── ALL FEATURE FLAGS ──

    @patch("services.config_db.get_supabase")
    def test_get_all_feature_flags(self, mock_get_supabase):
        from services.config_db import get_all_feature_flags

        mock_get_supabase.return_value = MockSupabaseClient(MockQueryBuilder(self.SAMPLE_FLAGS))
        result = get_all_feature_flags()
        assert len(result) == 1
        assert result[0]["key"] == "telegram_enabled"
