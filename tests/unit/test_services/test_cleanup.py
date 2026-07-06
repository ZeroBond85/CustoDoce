from unittest.mock import patch

from tests.unit.test_services.conftest import make_mocks


class TestCleanupService:
    @patch("services.maintenance_service.get_service_client")
    def test_cleanup_old_prices_calls_rpc(self, mock_get_client):
        """cleanup_old_prices() chama rpc('cleanup_old_prices')."""
        from services.price_service import cleanup_old_prices

        mock_client, _, qb = make_mocks()
        mock_get_client.return_value = mock_client

        result = cleanup_old_prices(retention_days=90)

        assert mock_client._captured_rpc is not None
        fn_name, params = mock_client._captured_rpc
        assert fn_name == "cleanup_old_prices"
        assert params == {"retention_days": 90}
        assert "deleted" in result

    @patch("services.maintenance_service.get_service_client")
    def test_cleanup_old_prices_default_retention(self, mock_get_client):
        """Usa 90 dias como padrao."""
        from services.price_service import cleanup_old_prices

        mock_client, _, _ = make_mocks()
        mock_get_client.return_value = mock_client

        cleanup_old_prices()

        assert mock_client._captured_rpc is not None
        _, params = mock_client._captured_rpc
        assert params == {"retention_days": 90}

    @patch("services.maintenance_service.get_service_client")
    def test_cleanup_old_logs_calls_rpc(self, mock_get_client):
        """cleanup_old_logs() chama rpc('cleanup_old_logs')."""
        from services.price_service import cleanup_old_logs

        mock_client, _, _ = make_mocks()
        mock_get_client.return_value = mock_client

        result = cleanup_old_logs(retention_days=30)

        assert mock_client._captured_rpc is not None
        fn_name, params = mock_client._captured_rpc
        assert fn_name == "cleanup_old_logs"
        assert params == {"retention_days": 30}
        assert "deleted" in result

    @patch("services.maintenance_service.get_service_client")
    def test_cleanup_old_logs_default_retention(self, mock_get_client):
        """Usa 30 dias como padrao."""
        from services.price_service import cleanup_old_logs

        mock_client, _, _ = make_mocks()
        mock_get_client.return_value = mock_client

        cleanup_old_logs()

        assert mock_client._captured_rpc is not None
        _, params = mock_client._captured_rpc
        assert params == {"retention_days": 30}

    @patch("services.flyer_service.get_service_client")
    def test_cleanup_old_flyers_calls_rpc(self, mock_get_client):
        """cleanup_old_flyers() chama rpc('cleanup_old_flyers')."""
        from services.flyer_service import cleanup_old_flyers

        mock_client, _, _ = make_mocks()
        mock_get_client.return_value = mock_client

        result = cleanup_old_flyers(retention_days=60)

        assert mock_client._captured_rpc is not None
        fn_name, params = mock_client._captured_rpc
        assert fn_name == "cleanup_old_flyers"
        assert params == {"retention_days": 60}
        assert "deleted" in result

    @patch("services.flyer_service.get_service_client")
    def test_cleanup_old_flyers_default_retention(self, mock_get_client):
        """Usa 60 dias como padrao."""
        from services.flyer_service import cleanup_old_flyers

        mock_client, _, _ = make_mocks()
        mock_get_client.return_value = mock_client

        cleanup_old_flyers()

        assert mock_client._captured_rpc is not None
        _, params = mock_client._captured_rpc
        assert params == {"retention_days": 60}
