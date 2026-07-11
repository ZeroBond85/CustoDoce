"""Unit tests for services/maintenance_service.py."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services import maintenance_service


@pytest.fixture
def tmp_track(tmp_path, monkeypatch):
    p = tmp_path / "cleanup_track.json"
    monkeypatch.setattr(maintenance_service, "_CLEANUP_TRACK_FILE", p)
    return p


def test_load_save_cleanup_track_roundtrip(tmp_track):
    maintenance_service._save_cleanup_track({"a": 1})
    assert tmp_track.exists()
    loaded = maintenance_service._load_cleanup_track()
    assert loaded == {"a": 1}


def test_load_cleanup_track_missing_returns_empty(tmp_track):
    assert maintenance_service._load_cleanup_track() == {}


def test_check_cleanup_alert_increments_zero_counter(tmp_track):
    for _ in range(3):
        maintenance_service._check_cleanup_alert("cleanup_old_prices", 0)
    track = json.loads(tmp_track.read_text(encoding="utf-8"))
    assert track["cleanup_old_prices_zero_days"] == 3
    assert track["cleanup_old_prices_last_deleted"] == 0


def test_check_cleanup_alert_resets_on_deletion(tmp_track):
    maintenance_service._check_cleanup_alert("cleanup_old_prices", 0)
    maintenance_service._check_cleanup_alert("cleanup_old_prices", 0)
    maintenance_service._check_cleanup_alert("cleanup_old_prices", 5)
    track = json.loads(tmp_track.read_text(encoding="utf-8"))
    assert track["cleanup_old_prices_zero_days"] == 0
    assert track["cleanup_old_prices_last_deleted"] == 5


def test_cleanup_old_prices_returns_deleted():
    mock_client = MagicMock()
    mock_client.rpc.return_value.execute.return_value = SimpleNamespace(data=5)
    with patch.object(maintenance_service, "get_service_client", return_value=mock_client):
        result = maintenance_service.cleanup_old_prices(90)
    assert result == {"deleted": 5}
    mock_client.rpc.assert_called_once_with("cleanup_old_prices", {"retention_days": 90})


def test_log_scraper_run_inserts():
    mock_client = MagicMock()
    mock_client.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
        data=[{"id": "log-x"}]
    )
    with patch.object(maintenance_service, "get_service_client", return_value=mock_client):
        result = maintenance_service.log_scraper_run("base_flyer", status="completed")
    assert result.get("id") == "log-x"
    sent = mock_client.table.return_value.insert.call_args[0][0]
    assert sent["store_name"] == "base_flyer"
    assert sent["status"] == "completed"
