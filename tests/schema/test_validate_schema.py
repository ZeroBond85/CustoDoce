#!/usr/bin/env python3
"""
Testes de schema do banco Supabase.
Valida que TODAS as tabelas, colunas, constraints, índices e funções esperadas existem.

Requer SUPABASE_URL e SUPABASE_DB_PASSWORD no .env.
Equivalente a: python scripts/validate_db_schema.py
"""

import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _has_db_creds():
    url = os.environ.get("SUPABASE_URL", "")
    pwd = os.environ.get("SUPABASE_DB_PASSWORD", "")
    if not url or not pwd:
        return False
    try:
        proj = url.split("//")[1].split(".")[0]
        return len(proj) > 10
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _has_db_creds(),
    reason="SUPABASE_URL / SUPABASE_DB_PASSWORD not set",
)


EXPECTED_TABLES = [
    "prices",
    "price_history",
    "review_queue",
    "scraping_logs",
    "stores",
    "flyers",
    "ingredients",
    "schedules",
    "scrape_frequencies",
    "alert_recipients",
    "alert_rules",
    "feature_flags",
    "recipes",
    "recipe_items",
]

EXPECTED_COLUMNS = {
    "prices": [
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
    ],
    "review_queue": [
        "id",
        "raw_product",
        "raw_price",
        "raw_unit",
        "store_name",
        "source",
        "confidence",
        "suggestions",
        "validity_raw",
        "status",
        "resolved_ingredient",
        "collected_at",
        "reviewed_at",
        "brand",
        "image_url",
        "source_url",
        "match_reason",
        "match_type",
        "top3",
    ],
    "ingredients": [
        "id",
        "canonical_name",
        "category",
        "aliases",
        "unit_target",
        "active",
        "created_at",
        "updated_at",
        "brands",
        "search_terms",
    ],
    "recipes": [
        "id",
        "name",
        "yield_qty",
        "overhead_pct",
        "profit_pct",
        "created_at",
    ],
    "recipe_items": [
        "id",
        "recipe_id",
        "ingredient_id",
        "quantity_g",
        "selected_store",
        "price_per_kg",
    ],
}

EXPECTED_CONSTRAINTS = {
    "prices": ["prices_ingredient_id_store_id_collected_at_key"],
    "price_history": ["price_history_ingredient_id_store_id_collected_at_key"],
}

EXPECTED_INDEXES = [
    "idx_prices_ing_collected",
    "idx_history_ing_collected",
    "idx_review_collected",
    "idx_stores_name",
    "idx_logs_store_started",
    "idx_recipe_items_recipe",
    "idx_prices_price_per_kg",  # generated column index
    "idx_prices_promo_collected",  # partial index
    "idx_prices_store_collected",  # FK index
    "idx_review_status_collected",  # review queue filter
    "idx_flyers_store_ocr_collected",  # flyer filter
    "idx_ingredients_active_name",  # active filter
]

EXPECTED_FUNCTIONS = [
    "upsert_price_rpc",
    "cleanup_old_prices",
    "cleanup_old_logs",
    "cleanup_old_flyers",
]


class TestSchemaTables:
    """14 tabelas esperadas."""

    @pytest.mark.parametrize("table_name", EXPECTED_TABLES)
    def test_table_exists(self, db_conn, table_name):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s;",
            (table_name,),
        )
        assert cur.fetchone(), f"Tabela '{table_name}' não existe"
        cur.close()


class TestSchemaColumns:
    """87 colunas esperadas."""

    @pytest.mark.parametrize("table,column", [(t, c) for t, cols in EXPECTED_COLUMNS.items() for c in cols])
    def test_column_exists(self, db_conn, table, column):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s;",
            (table, column),
        )
        assert cur.fetchone(), f"Coluna '{table}.{column}' não existe"
        cur.close()


class TestSchemaConstraints:
    """Constraints UNIQUE obrigatórias."""

    @pytest.mark.parametrize(
        "table,constraint_name", [(t, c) for t, names in EXPECTED_CONSTRAINTS.items() for c in names]
    )
    def test_constraint_exists(self, db_conn, table, constraint_name):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT 1 FROM pg_constraint WHERE conrelid = %s::regclass AND conname = %s;",
            (table, constraint_name),
        )
        assert cur.fetchone(), f"Constraint '{constraint_name}' não existe em '{table}'"
        cur.close()


class TestSchemaIndexes:
    """Índices de performance."""

    @pytest.mark.parametrize("index_name", EXPECTED_INDEXES)
    def test_index_exists(self, db_conn, index_name):
        cur = db_conn.cursor()
        cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s;", (index_name,))
        assert cur.fetchone(), f"Índice '{index_name}' não existe"
        cur.close()


class TestSchemaFunctions:
    """Funções RPC obrigatórias."""

    @pytest.mark.parametrize("function_name", EXPECTED_FUNCTIONS)
    def test_function_exists(self, db_conn, function_name):
        cur = db_conn.cursor()
        cur.execute("SELECT 1 FROM pg_proc WHERE proname = %s;", (function_name,))
        assert cur.fetchone(), f"Função '{function_name}()' não existe"
        cur.close()
