import socket
from unittest.mock import patch


from services.dns_resolver import resolve_hostname, check_url_reachable


def test_resolve_hostname_success():
    with patch("socket.getaddrinfo") as mock_getaddrinfo:
        mock_getaddrinfo.return_value = [
            (0, 0, 0, "", ("192.168.1.1", 0)),
            (0, 0, 0, "", ("10.0.0.1", 0)),
        ]
        ips = resolve_hostname("test.com", max_retries=1)
        assert ips is not None
        assert "192.168.1.1" in ips
        assert "10.0.0.1" in ips


def test_resolve_hostname_retry_then_success():
    with patch("socket.getaddrinfo") as mock_getaddrinfo:
        mock_getaddrinfo.side_effect = [
            socket.gaierror("Temporary failure"),
            [("test", "test", "test", "", ("1.2.3.4", 0))],
        ]
        ips = resolve_hostname("test.com", max_retries=2, delay=0.01)
        assert ips == ["1.2.3.4"]
        assert mock_getaddrinfo.call_count == 2


def test_resolve_hostname_all_fail():
    with patch("socket.getaddrinfo") as mock_getaddrinfo:
        mock_getaddrinfo.side_effect = socket.gaierror("Name or service not known")
        ips = resolve_hostname("nonexistent.example.com", max_retries=2, delay=0.01)
        assert ips is None
        assert mock_getaddrinfo.call_count == 2


def test_check_url_reachable_success():
    with patch("services.dns_resolver.resolve_hostname") as mock_resolve:
        mock_resolve.return_value = ["1.2.3.4"]
        assert check_url_reachable("https://test.com/path") is True
        mock_resolve.assert_called_once_with("test.com", max_retries=3)


def test_check_url_reachable_fail():
    with patch("services.dns_resolver.resolve_hostname") as mock_resolve:
        mock_resolve.return_value = None
        assert check_url_reachable("https://nonexistent.example.com") is False


def test_check_url_reachable_invalid():
    assert check_url_reachable("") is False


def test_resolve_hostname_strips_ipv6_scope():
    with patch("socket.getaddrinfo") as mock_getaddrinfo:
        mock_getaddrinfo.return_value = [
            (0, 0, 0, "", ("fe80::1%eth0", 0)),
        ]
        ips = resolve_hostname("test.com", max_retries=1)
        assert ips is not None
        assert "fe80::1" in ips
