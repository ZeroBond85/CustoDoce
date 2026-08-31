"""Testes de regressão Sprint 19 — F4 estrutural:
1. review_threshold default 0.70 → 0.82 (alinhado ao gate de persistência e5-large)
2. insert_review_item reabre rejeitados >=90d (re-entry sob UNIQUE constraint)
3. store_registry.expire_stale_pending expira pendências >30d
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import services.collector as collector
import services.review_queue_service as rqs
import services.store_registry as registry


# ── 1. Threshold default ─────────────────────────────────────────────────
def test_review_threshold_default_literal():
    # Garante que o LITERAL default no código é 0.82 (e5 gate recalibrado)
    import inspect

    src = inspect.getsource(collector)
    assert 'default=0.82' in src
    # O legado 0.70/0.80 não pode voltar como default do review_threshold
    assert 'default=0.70' not in src
    assert 'default=0.80' not in src


# ── 2. Re-entry de rejeitados ────────────────────────────────────────────
def _rq_client(existing: list[dict]):
    client = MagicMock()
    tbl = MagicMock()
    tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=existing)
    tbl.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "x"}])
    tbl.insert.return_value.execute.return_value = MagicMock(data=[{"id": "new"}])
    client.table.return_value = tbl
    return client, tbl


@patch("services.review_queue_service.get_service_client")
def test_reentry_rejeitado_antigo_reabre(mock_gsc):
    old_date = (datetime.now(UTC) - timedelta(days=120)).isoformat()
    client, tbl = _rq_client([{"id": "abc", "status": "rejected", "reviewed_at": old_date}])
    mock_gsc.return_value = client

    row = rqs.insert_review_item({"raw_product": "P", "store_name": "S", "confidence": 0.75})

    assert row["id"] == "abc"
    update_kwargs = tbl.update.call_args[0][0]
    assert update_kwargs["status"] == "pending"
    assert update_kwargs["confidence"] == 0.75


@patch("services.review_queue_service.get_service_client")
def test_reentry_rejeitado_recente_nao_reabre(mock_gsc):
    recent = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    client, tbl = _rq_client([{"id": "abc", "status": "rejected", "reviewed_at": recent}])
    mock_gsc.return_value = client

    rqs.insert_review_item({"raw_product": "P", "store_name": "S", "confidence": 0.75})

    tbl.update.assert_not_called()


@patch("services.review_queue_service.get_service_client")
def test_dedup_pending_nao_toca(mock_gsc):
    client, tbl = _rq_client([{"id": "abc", "status": "pending", "reviewed_at": None}])
    mock_gsc.return_value = client

    row = rqs.insert_review_item({"raw_product": "P", "store_name": "S"})

    assert row["status"] == "pending"
    tbl.update.assert_not_called()


@patch("services.review_queue_service.get_service_client")
def test_reentry_data_invalida_nao_explode(mock_gsc):
    client, tbl = _rq_client([{"id": "abc", "status": "rejected", "reviewed_at": "garbage"}])
    mock_gsc.return_value = client

    row = rqs.insert_review_item({"raw_product": "P", "store_name": "S"})

    assert row["id"] == "abc"
    tbl.update.assert_not_called()  # age_days=-1 < 90


# ── 3. Auto-expire registry ──────────────────────────────────────────────
def _reg_client(pending: list[dict]):
    client = MagicMock()
    tbl = MagicMock()
    upd = MagicMock()
    upd.eq.return_value.lt.return_value.execute.return_value = MagicMock(data=pending)
    tbl.update.return_value = upd
    client.table.return_value = tbl
    return client, tbl


@patch("services.store_registry.get_service_client")
def test_expire_stale_pending_expira(mock_gsc):
    pendings = [{"id": f"e{i}"} for i in range(3)]
    client, tbl = _reg_client(pendings)
    mock_gsc.return_value = client

    count = registry.expire_stale_pending(days=30)

    assert count == 3
    update_kwargs = tbl.update.call_args[0][0]
    assert update_kwargs["status"] == "expired"
    assert update_kwargs["reviewed_by"] == "auto-expire"


@patch("services.store_registry.get_service_client")
def test_expire_stale_pending_vazio(mock_gsc):
    client, _ = _reg_client([])
    mock_gsc.return_value = client
    assert registry.expire_stale_pending(days=30) == 0


@patch("services.store_registry.get_service_client")
def test_expire_stale_pending_erro_retorna_zero(mock_gsc):
    client = MagicMock()
    client.table.side_effect = Exception("db down")
    mock_gsc.return_value = client
    assert registry.expire_stale_pending(days=30) == 0
