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
    table.lt.side_effect = record
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
    mock_approve.assert_called_once_with(
        "a", "Manteiga", brand_override="", feedback_decision="auto_persist"
    )


def test_pick_auto_approve_ingredient_prioriza_top3():
    item = {
        "top3": [{"canonical_name": "Chocolate 70%"}, {"canonical_name": "Outro"}],
        "suggestions": ["Errado"],
    }
    assert rqs._pick_auto_approve_ingredient(item) == "Chocolate 70%"


@patch("services.review_queue_service.add_alias_to_ingredient")
@patch("services.price_repository.upsert_price")
@patch("services.review_queue_service.safe_execute")
@patch("services.review_queue_service.get_service_client")
def test_approve_review_item_loja_nao_resolvida_mantem_pending(mock_gsc, mock_safe, mock_upsert, mock_alias):
    """A6 (2026-09-05): loja não resolvida NÃO marca item como approved.

    Antes, approve_review_item resolvia store_id='' e mesmo assim fazia
    UPDATE status=approved no review_queue — preço nunca persistia (perda de
    dado + aprovação falsa). Agora retorna {} cedo e NÃO toca o status.
    """
    # _fetch_review_item usa o mesmo mock de client
    table = MagicMock()
    table.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
        data=[{"id": "r1", "store_name": "Loja Inexistente", "raw_product": "Produto X", "raw_price": 9.9}]
    )
    mock_gsc.return_value.table.return_value = table

    with patch.object(rqs, "_resolve_ingredient", return_value=("ing-1", {"canonical_name": "Manteiga"})), \
         patch.object(rqs, "_resolve_store", return_value=""):
        result = rqs.approve_review_item("r1", "Manteiga")

    assert result == {}
    mock_upsert.assert_not_called(), "não upserta sem store resolvida"
    mock_alias.assert_not_called()
    mock_safe.assert_not_called(), "não faz UPDATE status=approved sem store"


def test_pick_auto_approve_fallback_suggestions_string():
    import json

    item = {"top3": [], "suggestions": json.dumps(["Farinha de Trigo"])}
    assert rqs._pick_auto_approve_ingredient(item) == "Farinha de Trigo"


def test_pick_auto_approve_sem_candidato_retorna_vazio():
    assert rqs._pick_auto_approve_ingredient({"top3": [], "suggestions": []}) == ""


@patch("services.review_queue_service.approve_review_item")
@patch("services.review_queue_service.get_supabase")
def test_auto_approve_llm_confirmed_aprova_quando_llm_confirma(mock_gs, mock_approve):
    """Fase B1: aprova apenas quando o LLM confirma o top-1 com conf >= floor."""
    items = [
        {
            "id": "a",
            "confidence": 0.80,
            "raw_product": "Farinha Flocada Panko 1kg",
            "top3": [{"canonical_name": "Farinha de Trigo"}],
        },
        {
            "id": "b",
            "confidence": 0.81,
            "raw_product": "Farinha de Mandioca 1kg",
            "top3": [{"canonical_name": "Farinha de Trigo"}],
        },
    ]
    table, _ = _client_with(items)
    mock_gs.return_value.table.return_value = table
    mock_approve.return_value = {"status": "approved"}

    # item "a": LLM confirma (match=True, conf>=0.85, mesmo ingredient) → aprova
    # item "b": LLM discorda (match=False) → llm_failures, NÃO aprova
    llm_responses = [
        {"ingredient": "Farinha de Trigo", "confidence": 0.95, "match": True, "provider": "fake"},
        {"ingredient": None, "confidence": 0.0, "match": False, "provider": "fake"},
    ]
    with patch("parsers.llm_classifier.classify", side_effect=llm_responses):
        stats = rqs.auto_approve_llm_confirmed(
            threshold=0.78,
            dry_run=False,
        )

    assert stats == {"candidates": 2, "llm_failures": 1, "approved": 1, "failed": 0, "skipped": 0}
    mock_approve.assert_called_once_with(
        "a", "Farinha de Trigo", brand_override="", feedback_decision="llm_confirmed"
    )


@patch("services.review_queue_service.approve_review_item")
@patch("services.review_queue_service.get_supabase")
def test_auto_approve_llm_confirmed_dry_run_nao_aprova(mock_gs, mock_approve):
    items = [
        {
            "id": "a",
            "confidence": 0.80,
            "raw_product": "Farinha Flocada Panko 1kg",
            "top3": [{"canonical_name": "Farinha de Trigo"}],
        }
    ]
    table, _ = _client_with(items)
    mock_gs.return_value.table.return_value = table

    with patch(
        "parsers.llm_classifier.classify",
        return_value={"ingredient": "Farinha de Trigo", "confidence": 0.95, "match": True, "provider": "fake"},
    ):
        stats = rqs.auto_approve_llm_confirmed(threshold=0.78, dry_run=True)

    assert stats["candidates"] == 1
    assert stats["approved"] == 0
    mock_approve.assert_not_called()


@patch("services.review_queue_service.get_supabase")
def test_llm_verdict_rejeita_quando_llm_discorda(mock_gs):
    """b: LLM retorna match=False → llm_failures, sem aprovação."""
    item = {
        "id": "b",
        "confidence": 0.81,
        "raw_product": "Farinha de Mandioca 1kg",
        "top3": [{"canonical_name": "Farinha de Trigo"}],
    }
    stats = {"candidates": 1, "llm_failures": 0, "approved": 0, "failed": 0, "skipped": 0}

    def fake_classify(p, c):
        return {"ingredient": None, "confidence": 0.0, "match": False, "provider": "fake"}

    verdict = rqs._llm_verdict(item, "Farinha de Trigo", fake_classify, stats)

    assert verdict is False
    assert stats["llm_failures"] == 1


@patch("services.review_queue_service.get_supabase")
def test_llm_verdict_aprova_quando_llm_confirma(mock_gs):
    """a: LLM confirma o top-1 com conf >= floor → True."""
    item = {
        "id": "a",
        "confidence": 0.80,
        "raw_product": "Farinha Flocada Panko 1kg",
        "top3": [{"canonical_name": "Farinha de Trigo"}],
    }
    stats = {"candidates": 1, "llm_failures": 0, "approved": 0, "failed": 0, "skipped": 0}

    def fake_classify(p, c):
        return {"ingredient": "Farinha de Trigo", "confidence": 0.95, "match": True, "provider": "fake"}

    verdict = rqs._llm_verdict(item, "Farinha de Trigo", fake_classify, stats)

    assert verdict is True
    assert stats["llm_failures"] == 0
