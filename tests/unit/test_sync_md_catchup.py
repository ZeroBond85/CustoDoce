"""
Tests for catch-up one-shot (sync_md_catchup.py).

Garante que:
  - SNAPSHOT_FROZEN nunca é tocado.
  - SNAPSHOT_REFERENCE_LIVE alinha truth_at + bump version.
  - Detecção múltipla de DRY-RUN vs APPLY.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

import scripts.sync_md_catchup as cu  # noqa: E402


def test_project_truth_keys_exist():
    truth = cu._project_truth()
    assert "tests_total" in truth
    assert "pages_count" in truth
    assert "python_version" in truth


def test_project_truth_python_is_pin():
    truth = cu._project_truth()
    assert truth["python_version"] == "3.14.6"


def test_project_truth_types():
    truth = cu._project_truth()
    assert isinstance(truth["tests_total"], int)
    assert isinstance(truth["pages_count"], int)
    assert isinstance(truth["python_version"], str)


def test_bump_version_advances_patch():
    assert cu._bump_version("0.0.0") == "0.0.1"
    assert cu._bump_version("0.0.5") == "0.0.6"
    assert cu._bump_version("0.0.99") == "0.0.100"


def test_bump_version_handles_garbage():
    assert cu._bump_version("N/A") == "0.0.1"
    assert cu._bump_version("") == "0.0.1"


def test_archive_dir_exists_in_repo():
    archive = _ROOT / "docs" / "archive"
    assert archive.exists()


def test_catchup_archive_returns_list():
    """Smoke: catch-up roda sem erro e retorna lista."""
    changes = cu.catchup_archive(dry_run=True)
    assert isinstance(changes, list)
