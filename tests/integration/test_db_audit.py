"""
Testes de auditoria de banco de dados no Supabase real.
Cobre: contagem de tabelas, colunas, constraints, indexes, funções, triggers.
Usa db_conn (exec_sql_query RPC) para acessar schema do Postgres.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest


from tests.conftest import _has_real_db as _has_db_creds


pytestmark = pytest.mark.skipif(not _has_db_creds(), reason="Real DB creds not set")


class TestDBSchemaAudit:
    """Audita schema do Supabase real para garantir conformidade."""

    def test_tables_exist(self, db_conn):
        """Verifica que tabelas obrigatórias existem."""
        tables = [
            "prices",
            "price_history",
            "ingredients",
            "stores",
            "review_queue",
            "feature_flags",
            "alert_rules",
            "flyers",
            "scraping_logs",
        ]
        cur = db_conn.cursor()
        for t in tables:
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s;", (t,))
            assert cur.fetchone() is not None, f"Tabela {t} não existe"

    def test_prices_columns(self, db_conn):
        """Verifica colunas obrigatórias na tabela prices."""
        cols = [
            "id",
            "ingredient_id",
            "store_id",
            "source",
            "store_name",
            "raw_product",
            "raw_price",
            "raw_unit",
            "collected_at",
            "valid_from",
            "valid_until",
            "validity_raw",
            "collected_weekday",
            "is_promotion",
            "tier",
            "confidence",
            "normalized",
            "city",
            "logistics",
            "brand",
            "price_per_kg",
            "created_at",
        ]
        cur = db_conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'prices';", ())
        existing = {row[0] for row in cur.fetchall()}
        for c in cols:
            assert c in existing, f"Coluna {c} ausente na tabela prices"

    def test_price_history_columns(self, db_conn):
        """Verifica colunas obrigatórias na tabela price_history."""
        cols = [
            "id",
            "ingredient_id",
            "store_id",
            "store_name",
            "raw_product",
            "raw_price",
            "raw_unit",
            "collected_at",
            "valid_from",
            "valid_until",
            "validity_raw",
            "collected_weekday",
            "is_promotion",
            "normalized",
            "logistics",
            "brand",
            "price_per_kg",
            "created_at",
        ]
        cur = db_conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'price_history';", ())
        existing = {row[0] for row in cur.fetchall()}
        for c in cols:
            assert c in existing, f"Coluna {c} ausente na tabela price_history"

    def test_stores_columns(self, db_conn):
        """Verifica colunas obrigatórias na tabela stores."""
        cols = [
            "id",
            "name",
            "tier",
            "city",
            "logistics",
            "is_active",
            "visit_frequency",
            "url_pattern",
        ]
        cur = db_conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'stores';", ())
        existing = {row[0] for row in cur.fetchall()}
        for c in cols:
            assert c in existing, f"Coluna {c} ausente na tabela stores"

    def test_ingredients_columns(self, db_conn):
        """Verifica colunas obrigatórias na tabela ingredients."""
        cols = [
            "id",
            "canonical_name",
            "aliases",
            "category",
            "brands",
            "active",
        ]
        cur = db_conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'ingredients';", ())
        existing = {row[0] for row in cur.fetchall()}
        for c in cols:
            assert c in existing, f"Coluna {c} ausente na tabela ingredients"

    def test_review_queue_columns(self, db_conn):
        """Verifica colunas obrigatórias na tabela review_queue."""
        cols = [
            "id",
            "raw_product",
            "raw_price",
            "raw_unit",
            "store_name",
            "source",
            "confidence",
            "status",
            "match_type",
            "match_reason",
            "top3",
            "brand",
            "collected_at",
        ]
        cur = db_conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'review_queue';", ())
        existing = {row[0] for row in cur.fetchall()}
        for c in cols:
            assert c in existing, f"Coluna {c} ausente na tabela review_queue"

    def test_feature_flags_columns(self, db_conn):
        """Verifica colunas obrigatórias na tabela feature_flags."""
        cols = [
            "key",
            "enabled",
            "created_at",
            "updated_at",
        ]
        cur = db_conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'feature_flags';", ())
        existing = {row[0] for row in cur.fetchall()}
        for c in cols:
            assert c in existing, f"Coluna {c} ausente na tabela feature_flags"

    def test_alerts_columns(self, db_conn):
        """Verifica colunas obrigatórias na tabela alert_rules."""
        cols = [
            "id",
            "name",
            "channel",
            "trigger",
            "condition",
            "frequency_minutes",
            "recipients",
            "template",
            "enabled",
            "created_at",
            "updated_at",
        ]
        cur = db_conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'alert_rules';", ())
        existing = {row[0] for row in cur.fetchall()}
        for c in cols:
            assert c in existing, f"Coluna {c} ausente na tabela alert_rules"

    def test_flyers_columns(self, db_conn):
        """Verifica colunas obrigatórias na tabela flyers."""
        cols = [
            "id",
            "store_name",
            "region",
            "image_url",
            "image_hash",
            "collected_at",
        ]
        cur = db_conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'flyers';", ())
        existing = {row[0] for row in cur.fetchall()}
        for c in cols:
            assert c in existing, f"Coluna {c} ausente na tabela flyers"

    def test_logs_columns(self, db_conn):
        """Verifica colunas obrigatórias na tabela scraping_logs."""
        cols = [
            "id",
            "status",
            "created_at",
        ]
        cur = db_conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'scraping_logs';", ())
        existing = {row[0] for row in cur.fetchall()}
        for c in cols:
            assert c in existing, f"Coluna {c} ausente na tabela scraping_logs"

    def test_indexes_exist(self, db_conn):
        """Verifica que indexes obrigatórios existem."""
        indexes = [
            "idx_prices_store_collected",
            "idx_prices_price_per_kg",
            "price_history_ingredient_id_store_id_collected_at_key",
            "idx_review_queue_store_product",
            "idx_alerts_ingredient_store_active",
            "idx_flyers_store_active",
        ]
        cur = db_conn.cursor()
        cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'public';", ())
        existing = {row[0] for row in cur.fetchall()}
        for idx in indexes:
            assert idx in existing, f"Index {idx} ausente"

    def test_functions_exist(self, db_conn):
        """Verifica que funções obrigatórias existem."""
        funcs = [
            "upsert_price_rpc",
            "cleanup_old_prices",
            "cleanup_old_logs",
            "cleanup_old_flyers",
            "exec_sql_query",
        ]
        cur = db_conn.cursor()
        cur.execute("SELECT routine_name FROM information_schema.routines WHERE routine_schema = 'public';", ())
        existing = {row[0] for row in cur.fetchall()}
        for f in funcs:
            assert f in existing, f"Função {f} ausente"

    def test_triggers_exist(self, db_conn):
        """Verifica que triggers obrigatórios existem."""
        triggers = [
            "trg_price_history",
        ]
        cur = db_conn.cursor()
        cur.execute("SELECT trigger_name FROM information_schema.triggers WHERE trigger_schema = 'public';", ())
        existing = {row[0] for row in cur.fetchall()}
        for t in triggers:
            assert t in existing, f"Trigger {t} ausente"

    def test_constraints_unique(self, db_conn):
        """Verifica constraints UNIQUE obrigatórias."""
        constraints = [
            "prices_ingredient_id_store_id_collected_at_key",
            "price_history_ingredient_id_store_id_collected_at_key",
            "review_queue_store_name_raw_product_key",
        ]
        cur = db_conn.cursor()
        cur.execute("SELECT conname FROM pg_constraint WHERE contype = 'u';", ())
        existing = {row[0] for row in cur.fetchall()}
        for c in constraints:
            assert c in existing, f"Constraint UNIQUE {c} ausente"

    def test_materialized_views_exist(self, db_conn):
        """Verifica que materialized views obrigatórias existem."""
        views = [
            "v_latest_prices",
        ]
        cur = db_conn.cursor()
        cur.execute("SELECT matviewname FROM pg_matviews WHERE schemaname = 'public';", ())
        existing = {row[0] for row in cur.fetchall()}
        for v in views:
            assert v in existing, f"Materialized view {v} ausente"

    def test_generated_columns_exist(self, db_conn):
        """Verifica que generated columns obrigatórios existem."""
        cols = [
            "price_per_kg",
        ]
        cur = db_conn.cursor()
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'prices' AND is_generated = 'ALWAYS';",
            (),
        )
        existing = {row[0] for row in cur.fetchall()}
        for c in cols:
            assert c in existing, f"Generated column {c} ausente"
