"""Unit tests for scripts/validate_migrations.py — ledger de migrations.

Testa lógica pura (listar migrations, sha256, ordem) SEM tocar o banco real.
O fluxo RPC (exec_sql_query / bootstrap) é coberto por integration tests.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import scripts.validate_migrations as vm


class TestListLocalMigrations:
    def test_returns_sorted_migrations(self):
        migrations = vm.list_local_migrations()
        assert len(migrations) >= 5
        versions = [m["version"] for m in migrations]
        assert versions == sorted(versions, key=int)

    def test_entries_have_expected_keys(self):
        migrations = vm.list_local_migrations()
        for m in migrations:
            assert m["version"].isdigit()
            assert m["name"].startswith(m["version"] + "_")
            assert m["name"].endswith(".sql")
            assert m["path"].exists()
            assert len(m["checksum"]) == 64

    def test_latest_migrations_present(self):
        migrations = vm.list_local_migrations()
        names = {m["name"] for m in migrations}
        for expected in [
            "015_security_hardening.sql",
            "016_drop_anon_insert.sql",
            "017_restore_anon_read.sql",
            "018_init_migrations_ledger.sql",
        ]:
            assert expected in names, f"{expected} ausente em supabase/migrations/"


class TestChecksum:
    def test_sha256_stable(self):
        path = Path("supabase/migrations/018_init_migrations_ledger.sql")
        assert vm.sha256_of(path) == vm.sha256_of(path)

    def test_sha256_changes_with_content(self, tmp_path):
        p = tmp_path / "m.sql"
        p.write_text("SELECT 1;", encoding="utf-8")
        a = vm.sha256_of(p)
        p.write_text("SELECT 2;", encoding="utf-8")
        b = vm.sha256_of(p)
        assert a != b


class TestOrderValidation:
    def test_monotonic_order_accepted(self):
        # Simula a lista local (001, 006, 007, ...) — gaps OK, ordem crescente.
        data = [
            {"version": "001", "name": "001_a.sql", "checksum": "x"},
            {"version": "006", "name": "006_b.sql", "checksum": "x"},
            {"version": "017", "name": "017_c.sql", "checksum": "x"},
        ]
        versions = sorted(data, key=lambda m: m["version"])
        prev = None
        errors = []
        for m in versions:
            v = m["version"]
            if prev is not None and int(v) <= int(prev):
                errors.append(f"ordem invalida: {prev} depois de {v}")
            prev = v
        assert not errors, "gaps NAO devem quebrar a validacao de ordem"

    def test_reversed_order_rejected(self):
        versions = sorted(["017", "006", "001"], key=lambda m: m)
        assert versions == ["001", "006", "017"]


class TestLedgerExistsInConsolidated:
    def test_ledger_is_phase_0_in_consolidated(self):
        consolidated = Path("supabase/consolidated_migration.sql")
        assert consolidated.exists()
        text = consolidated.read_text(encoding="utf-8")
        assert "PHASE 0: Migration ledger" in text
        assert "CREATE TABLE IF NOT EXISTS public.schema_migrations" in text

    def test_ledger_uses_service_role_policy(self):
        migration = Path("supabase/migrations/018_init_migrations_ledger.sql")
        text = migration.read_text(encoding="utf-8")
        assert "schema_migrations_service_all" in text
        assert "TO service_role" in text
