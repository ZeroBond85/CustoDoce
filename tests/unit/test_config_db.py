from unittest.mock import MagicMock


def test_get_ingredient_by_name():
    from unittest.mock import patch

    from services.config_db import get_ingredient_by_name

    with patch("services.config_db.get_supabase") as mock_get_supabase:
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data={"id": "uuid-1", "canonical_name": "Leite Condensado"}
        )
        mock_get_supabase.return_value = mock_client
        result = get_ingredient_by_name("Leite Condensado")
        assert result == {"id": "uuid-1", "canonical_name": "Leite Condensado"}


def test_get_ingredient_by_name_none():
    from unittest.mock import patch

    from services.config_db import get_ingredient_by_name

    with patch("services.config_db.get_supabase") as mock_get_supabase:
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_get_supabase.return_value = mock_client
        result = get_ingredient_by_name("Nonexistent")
        assert result is None


def test_get_active_ingredients():
    from unittest.mock import patch

    from services.config_db import get_active_ingredients

    with patch("services.config_db.get_supabase") as mock_get_supabase:
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = (
            MagicMock(data=[{"id": "1", "canonical_name": "Ing 1"}, {"id": "2", "canonical_name": "Ing 2"}])
        )
        mock_get_supabase.return_value = mock_client
        result = get_active_ingredients()
        assert len(result) == 2
        assert result[0]["id"] == "1"


def test_upsert_store_validation():
    test_cases = [
        ({"name": "Store A", "tier": 1}, False),
        ({"name": "Store B", "tier": 0}, True),
        ({"name": "Store C", "tier": 5}, True),
        ({"name": "Store D", "tier": "invalid"}, True),
        ({"name": "Store E", "priority": 10}, False),
        ({"name": "Store F", "priority": -1}, True),
        ({"name": "Store G", "priority": "invalid"}, True),
    ]

    from unittest.mock import patch

    from services.config_db import upsert_store

    for store_data, expected_raise in test_cases:
        with patch("services.config_db.get_service_client") as mock_get_service_client:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_result.data = [store_data]
            mock_client.table.return_value.upsert.return_value.execute.return_value = mock_result
            mock_get_service_client.return_value = mock_client

            if expected_raise:
                try:
                    upsert_store(store_data)
                    raise AssertionError(f"Expected ValueError for {store_data}")
                except ValueError:
                    pass  # Expected
            else:
                result = upsert_store(store_data)
                assert result != {}
                assert result["name"] == store_data["name"]


def test_get_feature_flag():
    test_cases = [
        ("feature.ai", {"enabled": True}, False, True),
        ("feature.off", {"enabled": False}, True, False),
        ("feature.missing", None, True, True),
        ("feature.missing", None, False, False),
    ]

    from unittest.mock import patch

    from services.config_db import get_feature_flag

    for key, mock_data, default, expected in test_cases:
        with patch("services.config_db.get_supabase") as mock_get_supabase:
            mock_client = MagicMock()
            # Mock the full chain: table("feature_flags").select("enabled").eq("key", key).maybe_single().execute()
            mock_execute_result = MagicMock()
            # Extract the enabled value from mock_data if it's not None
            if mock_data is not None:
                mock_execute_result.data = {"enabled": bool(mock_data.get("enabled", False))}
            else:
                mock_execute_result.data = None
            mock_maybe_single = MagicMock()
            mock_maybe_single.execute.return_value = mock_execute_result
            mock_eq = MagicMock()
            mock_eq.maybe_single.return_value = mock_maybe_single
            mock_select = MagicMock()
            mock_select.eq.return_value = mock_eq
            mock_table = MagicMock()
            mock_table.select.return_value = mock_select
            mock_client.table.return_value = mock_table
            mock_get_supabase.return_value = mock_client
            result = get_feature_flag(key, default)
            assert result == expected, f"Failed for key={key}, mock_data={mock_data}, default={expected}"


def test_get_active_stores_paginates_beyond_1000():
    from unittest.mock import patch

    from services.config_db import get_active_stores

    batches = [
        [{"id": str(i), "is_active": True} for i in range(1000)],
        [{"id": str(i)} for i in range(1000, 1200)],
    ]
    with patch("services.config_db.get_supabase") as mock_get_supabase:
        mock_client = MagicMock()
        query = MagicMock()
        query.range.side_effect = [
            MagicMock(execute=MagicMock(return_value=MagicMock(data=batches[0]))),
            MagicMock(execute=MagicMock(return_value=MagicMock(data=batches[1]))),
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value = query
        mock_get_supabase.return_value = mock_client

        result = get_active_stores()

        assert len(result) == 1200
        assert query.range.call_count == 2


def test_test_single_store_fails_on_zero_products():
    import sys
    from unittest.mock import patch

    import scripts.test_single_store as t

    store = {"name": "X", "type": "website_js", "scraper": "playwright_price_scraper"}
    with patch.object(t, "get_store_by_name", return_value=store), patch.object(
        t, "load_ingredients", return_value=[]
    ), patch("services.collector.load_stores", return_value=[store]), patch(
        "services.collector.collect_tier2_js", new=lambda ingredients: []
    ), patch.object(sys, "argv", ["test_single_store.py", "X"]):
        rc = t.main()

    assert rc == 1


def test_test_single_store_resolves_paused_store():
    import sys
    from unittest.mock import patch

    import scripts.test_single_store as t

    store = {"name": "Paused", "type": "website_js", "scraper": "playwright_price_scraper"}
    with patch.object(t, "get_store_by_name", return_value=store), patch.object(
        t, "load_ingredients", return_value=[]
    ), patch("services.collector.load_stores", return_value=[store]), patch(
        "services.collector.collect_tier2_js", new=lambda ingredients: [{"name": "p"}]
    ), patch.object(sys, "argv", ["test_single_store.py", "Paused"]):
        rc = t.main()

    assert rc == 0
