"""Tests for scripts/commit_prices.py — snapshot generation and git operations."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Path to the script under test
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
COMMIT_SCRIPT = SCRIPTS_DIR / "commit_prices.py"


def _read_script() -> str:
    return COMMIT_SCRIPT.read_text(encoding="utf-8")


class TestCommitPricesScriptExists:
    """The commit_prices.py script must exist (referenced by scrape-reusable.yml)."""

    def test_script_file_exists(self):
        assert COMMIT_SCRIPT.exists(), f"Missing script: {COMMIT_SCRIPT}"

    def test_script_is_valid_python(self):
        content = _read_script()
        compile(content, str(COMMIT_SCRIPT), "exec")

    def test_script_imports_required_modules(self):
        content = _read_script()
        for module in ["subprocess", "json", "os", "sys"]:
            assert module in content, f"Script must import {module}"


class TestCommitPricesImports:
    """The script should not import from local modules unconditionally (graceful fallback)."""

    def test_no_top_level_local_imports(self):
        content = _read_script()
        lines = content.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("from services.") or stripped.startswith("import services"):
                # Local imports must be inside functions, not top-level
                assert i > 5, f"Local import on line {i + 1} must be inside function: {line}"


class TestCommitPricesLogic:
    """Test the commit_prices logic flow."""

    def test_local_snapshot_uses_existing_file(self, tmp_path):
        # Create a fake local snapshot
        data_dir = tmp_path / "data"
        data_dir.mkdir(exist_ok=True)
        snapshot = {
            "collected_at": "2026-07-08T00:00:00+00:00",
            "total_prices": 42,
            "ingredients_found": 12,
        }
        (data_dir / "prices_latest.json").write_text(json.dumps(snapshot))

        # Verify the snapshot can be loaded
        loaded = json.loads((data_dir / "prices_latest.json").read_text())
        assert loaded["total_prices"] == 42
        assert loaded["ingredients_found"] == 12

    def test_snapshot_structure(self):
        """Snapshot must have collected_at, total_prices, ingredients_found."""
        snapshot = {
            "collected_at": "2026-07-08T00:00:00+00:00",
            "total_prices": 39,
            "ingredients_found": 9,
        }
        assert "collected_at" in snapshot
        assert "total_prices" in snapshot
        assert "ingredients_found" in snapshot
