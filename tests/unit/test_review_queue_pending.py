"""Regressão: Fila de Revisão mostrava "500 pendentes" quando o banco tinha 1598.

Duas causas-raiz (produção, 2026-08-21):
1. get_review_queue() SEM filtro de status — misturava approved/rejected/resolved
   com pending na mesma listagem e na métrica "Total Pendentes".
2. limit=500 hardcoded escondia o backlog real.

Fix: .eq("status","pending") + get_review_queue_pending_count() (count="exact")
+ auto_approve_high_confidence() com dry_run.
"""

from unittest.mock import MagicMock, patch

import services.review_queue_service as rqs


def _client_with(items: list[dict], count: int = 0):
    """Mock do client Supabase que captura a query encadeada."""
    captured = {}

    table = MagicMock()

    def record(*args, **kwargs):
        if args:
            captured[args[0]] = args[1] if len(args) > 1 else True
        captured.update(kwargs)
        return table

    table.select.side_effect = lambda *a, **kw: table
    table.eq.side_effect = record
    table.gte.side_effect = record
    table.order.side_effect = record
    table.limit.side_effect = record
    table.execute.return_value = MagicMock(data=items, count=count)
    return table, captured


@patch("services.review_queue_service.get_supabase")
def test_get_review_queue_filtra_status_pending(mock_gs):
    items = [{"id": "1", "status": "pending"}]
    table, captured = _client_with(items)
    mock_gs.return_value.table.return_value = table

    result = rqs.get_review_queue(limit=100)

    assert result == items
    # FIX RAIZ: filtro de status obrigatório
    assert captured.get("status") == "pending"


@patch("services.review_queue_service.get_supabase")
def test_pending_count_usa_count_exact(mock_gs):
    table, _ = _client_with([], count=1598)
    mock_gs.return_value.table.return_value = table

    total = rqs.get_review_queue_pending_count()

    assert total == 1598


@patch("services.review_queue_service.approve_review_item")
@patch("services.review_queue_service.get_supabase")
def test_auto_approve_dry_run_nao_aprova(mock_gs, mock_approve):
    items = [{"id": "a", "confidence": 0.85, "top3": [{"canonical_name": "Manteiga"}]}]
    table, _ = _client_with(items)
    mock_gs.return_value.table.return_value = table

    stats = rqs.auto_approve_high_confidence(threshold=0.80, dry_run=True)

    assert stats == {"candidates": 1, "approved": 0, "failed": 0, "skipped": 0}
    mock_approve.assert_not_called()


@patch("services.review_queue_service.approve_review_item")
@patch("services.review_queue_service.get_supabase")
def test_auto_approve_executa_e_contabiliza(mock_gs, mock_approve):
    items = [
        {"id": "a", "confidence": 0.9, "top3": [{"canonical_name": "Manteiga"}]},
        {"id": "b", "confidence": 0.82, "top3": []},
    ]
    table, _ = _client_with(items)
    mock_gs.return_value.table.return_value = table
    mock_approve.side_effect = [{"status": "approved"}, {}]

    stats = rqs.auto_approve_high_confidence(threshold=0.80, dry_run=False)

    assert stats["candidates"] == 2
    assert stats["approved"] == 1
    assert stats["failed"] == 0
    assert stats["skipped"] == 1  # item "b" sem candidato top3/suggestions
    mock_approve.assert_called_once_with("a", "Manteiga", brand_override="")


def test_pick_auto_approve_ingredient_prioriza_top3():
    item = {
        "top3": [{"canonical_name": "Chocolate 70%"}, {"canonical_name": "Outro"}],
        "suggestions": ["Errado"],
    }
    assert rqs._pick_auto_approve_ingredient(item) == "Chocolate 70%"


def test_pick_auto_approve_fallback_suggestions_string():
    import json

    item = {"top3": [], "suggestions": json.dumps(["Farinha de Trigo"])}
    assert rqs._pick_auto_approve_ingredient(item) == "Farinha de Trigo"


def test_pick_auto_approve_sem_candidato_retorna_vazio():
    assert rqs._pick_auto_approve_ingredient({"top3": [], "suggestions": []}) == ""
