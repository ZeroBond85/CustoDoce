from unittest.mock import MagicMock, patch

import pytest

from services.price_service import (
    _detect_promotion,
    batch_upsert_prices,
    cleanup_old_prices,
    search_prices,
    upsert_price,
)


@pytest.fixture
def mock_supabase():
    with (
        patch("services.supabase_client.get_service_client") as mock_get,
        patch("services.price_repository.get_service_client") as mock_get_repo,
        patch("services.maintenance_service.get_service_client") as mock_get_maint,
    ):
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_get_repo.return_value = mock_client
        mock_get_maint.return_value = mock_client
        yield mock_client


@pytest.mark.parametrize(
    "raw_product, raw_unit, expected",
    [
        ("Leite Condensado Moça Promo", "395g", True),
        ("Creme de Leite Oferta", "200g", True),
        ("Chocolate 10% OFF", "1kg", True),
        ("Açúcar com desconto", "1kg", True),
        ("Promoção de Natal", "500g", True),
        ("Leite Condensado Normal", "395g", False),
        ("Creme de Leite", "200g", False),
        ("Chocolate", "1kg", False),
        ("", "", False),
        ("12345", "6789", False),
    ],
)
def test_detect_promotion(raw_product, raw_unit, expected):
    assert _detect_promotion(raw_product, raw_unit) == expected


@pytest.mark.parametrize(
    "price_entry, mock_response, expected_id",
    [
        # Success case
        (
            {"ingredient_id": "ing1", "store_id": "st1", "raw_product": "Prod 1", "raw_price": 10.0, "raw_unit": "1kg"},
            {"data": {"id": "uuid-1"}},
            "uuid-1",
        ),
        # List response
        (
            {"ingredient_id": "ing1", "store_id": "st1", "raw_product": "Prod 1", "raw_price": 10.0, "raw_unit": "1kg"},
            {"data": [{"id": "uuid-2"}]},
            "uuid-2",
        ),
        # Empty response
        (
            {"ingredient_id": "ing1", "store_id": "st1", "raw_product": "Prod 1", "raw_price": 10.0, "raw_unit": "1kg"},
            {"data": []},
            None,
        ),
    ],
)
def test_upsert_price_success(mock_supabase, price_entry, mock_response, expected_id):
    mock_supabase.rpc().execute.return_value = MagicMock(data=mock_response["data"])
    result = upsert_price(price_entry)
    if expected_id:
        assert result.get("id") == expected_id
    else:
        assert result == {}


def test_upsert_price_fallback(mock_supabase):
    # RPC fails, trigger fallback to table.upsert (with on_conflict, no 23505)
    mock_supabase.rpc().execute.side_effect = Exception("RPC Error")
    tbl = mock_supabase.table.return_value
    tbl.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "fallback-id"}])

    price_entry = {
        "ingredient_id": "ing1",
        "store_id": "st1",
        "raw_product": "Prod 1",
        "raw_price": 10.0,
        "raw_unit": "1kg",
    }
    result = upsert_price(price_entry)
    assert result.get("id") == "fallback-id"
    assert tbl.upsert.call_args is not None


@pytest.mark.parametrize(
    "sort_by, sort_order, expected_order_call",
    [
        ("price_per_kg", "asc", ("price_per_kg", False)),
        ("price_per_kg", "desc", ("price_per_kg", True)),
        ("price_per_un", "asc", ("price_per_un", False)),
        ("raw_price", "asc", ("raw_price", False)),
        ("collected_at", "desc", ("collected_at", True)),
    ],
)
def test_search_prices_sorting(mock_supabase, sort_by, sort_order, expected_order_call):
    with patch("services.price_repository.get_supabase", return_value=mock_supabase):
        mock_supabase.table().select().eq().lte().gte().order().limit().execute.return_value = MagicMock(data=[])
        search_prices("ing1", sort_by=sort_by, sort_order=sort_order)

        # Verify order call
        args, kwargs = mock_supabase.table().select().eq().lte().gte().order.call_args
        assert args[0] == expected_order_call[0]
        assert kwargs["desc"] == expected_order_call[1]


@pytest.mark.parametrize(
    "deleted_count, expected_log_alert",
    [
        (10, False),
        (0, False),  # First day zero is not alert
    ],
)
def test_cleanup_old_prices_logging(mock_supabase, deleted_count, expected_log_alert):
    mock_supabase.rpc().execute.return_value = MagicMock(data=deleted_count)
    with patch("services.maintenance_service._check_cleanup_alert") as mock_alert:
        cleanup_old_prices(90)
        mock_alert.assert_called_once_with("cleanup_old_prices", deleted_count)


def _make_entry(ing_id, store_id, raw_price, product="Leite Condensado Moça 395g"):
    return {
        "ingredient_id": ing_id,
        "store_id": store_id,
        "raw_product": product,
        "raw_price": raw_price,
        "raw_unit": "395g",
        "source": "automated",
    }


def test_batch_upsert_prices_empty():
    with patch("services.price_repository.get_service_client") as mock_get:
        result = batch_upsert_prices([])
    assert result == {"total": 0, "inserted": 0, "failed": 0}
    mock_get.assert_not_called()


def test_batch_upsert_prices_single_chunk(mock_supabase):
    """Batch flushes N entries em UMA chamada table.upsert (não 1 request por produto)."""
    mock_supabase.table().upsert.return_value.execute.return_value = MagicMock(
        data=[{"ingredient_id": "a"}, {"ingredient_id": "b"}]
    )
    entries = [
        _make_entry("ing1", "st1", 10.0),
        _make_entry("ing1", "st2", 12.5),
    ]
    result = batch_upsert_prices(entries)

    assert result == {"total": 2, "inserted": 2, "failed": 0}
    # Uma única chamada upsert com os 2 rows
    assert mock_supabase.table().upsert.call_count == 1
    rows = mock_supabase.table().upsert.call_args.args[0]
    assert isinstance(rows, list) and len(rows) == 2
    assert rows[0]["ingredient_id"] == "ing1"
    assert rows[0]["store_id"] == "st1"
    assert rows[1]["store_id"] == "st2"


def test_batch_upsert_prices_chunks_by_chunk_size(mock_supabase):
    """Chunk_size=2 → 5 entries viram 3 chamadas upsert."""
    mock_supabase.table().upsert.return_value.execute.return_value = MagicMock(data=[])
    entries = [_make_entry(f"ing{i}", f"st{i}", float(i)) for i in range(5)]
    result = batch_upsert_prices(entries, chunk_size=2)

    assert result == {"total": 5, "inserted": 0, "failed": 0}
    assert mock_supabase.table().upsert.call_count == 3


def test_batch_upsert_prices_deduplicates_same_key(mock_supabase):
    """Regressão P0: ON CONFLICT DO UPDATE não pode afetar a mesma row 2x no
    mesmo chunk. Duplicatas de (ingredient_id, store_id) com mesmo collected_at
    devem ser deduplicadas mantendo o menor price_per_kg."""
    mock_supabase.table().upsert.return_value.execute.return_value = MagicMock(data=[])
    entries = [
        _make_entry("ing1", "st1", 10.0),
        _make_entry("ing1", "st1", 8.5),  # melhor preço
        _make_entry("ing1", "st1", 12.0),
        _make_entry("ing1", "st2", 5.0),  # store diferente, não dedup
    ]
    result = batch_upsert_prices(entries, chunk_size=10)

    assert result["total"] == 2, "duplicatas devem ser colapsadas para 2 rows"
    rows = mock_supabase.table().upsert.call_args.args[0]
    assert len(rows) == 2
    by_store = {r["store_id"]: r for r in rows}
    assert by_store["st1"]["raw_price"] == 8.5, "deve manter o melhor (menor) preço"
    assert by_store["st2"]["raw_price"] == 5.0


def test_batch_upsert_prices_partial_failure(mock_supabase):
    """Chunk com erro persistente conta como failed e não derruba os demais."""
    # 1º chunk OK (retorna 2 rows), 2º chunk levanta exceção
    calls = {"n": 0}

    def _side_effect(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return MagicMock(data=[{"ingredient_id": "a"}, {"ingredient_id": "b"}])
        raise RuntimeError("DB down")

    mock_supabase.table().upsert.return_value.execute.side_effect = _side_effect
    entries = [_make_entry(f"ing{i}", f"st{i}", float(i)) for i in range(5)]
    result = batch_upsert_prices(entries, chunk_size=2)

    assert result["total"] == 5
    assert result["inserted"] == 2
    assert result["failed"] == 3


def test_batch_upsert_prices_preserves_build_row_logic(mock_supabase):
    """Rows do batch devem ter os campos default do fallback unitário (brand, valid_until, weekday)."""
    mock_supabase.table().upsert.return_value.execute.return_value = MagicMock(data=[])
    entry = _make_entry("ing1", "st1", 10.0)
    batch_upsert_prices([entry])

    rows = mock_supabase.table().upsert.call_args.args[0]
    row = rows[0]
    assert row["brand"] == "Desconhecido"
    assert row["confidence"] == 1.0
    assert row["collected_weekday"] in ("Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom")
    assert row["valid_until"] >= row["valid_from"]
    assert row["source"] == "automated"
