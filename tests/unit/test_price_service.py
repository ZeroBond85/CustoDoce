from unittest.mock import MagicMock, patch

import pytest

from services.price_service import _detect_promotion, cleanup_old_prices, search_prices, upsert_price


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
