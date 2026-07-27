import httpx

from services.error_classifier import ErrorCategory, ErrorSeverity, classify_error


def test_dns_error():
    exc = httpx.ConnectError("getaddrinfo failed for test.com:443")
    result = classify_error(exc, context="assai")
    assert result.category == ErrorCategory.DNS
    assert result.severity == ErrorSeverity.MEDIUM
    assert result.should_retry is True
    assert "DNS" in result.message


def test_connect_error():
    exc = httpx.ConnectError("connection refused")
    result = classify_error(exc, context="store")
    assert result.category == ErrorCategory.NETWORK
    assert result.should_retry is True


def test_timeout():
    exc = httpx.TimeoutException("timed out")
    result = classify_error(exc, context="api")
    assert result.category == ErrorCategory.TIMEOUT
    assert result.should_retry is True


def test_network_error():
    exc = httpx.NetworkError("network unreachable")
    result = classify_error(exc, context="scraper")
    assert result.category == ErrorCategory.NETWORK
    assert result.severity == ErrorSeverity.HIGH
    assert result.should_alert is True


def test_remote_protocol_error():
    exc = httpx.RemoteProtocolError("connection closed")
    result = classify_error(exc, context="store")
    assert result.category == ErrorCategory.NETWORK
    assert result.should_retry is True


def test_429_rate_limit():
    request = httpx.Request("GET", "http://test.com")
    response = httpx.Response(429, request=request)
    exc = httpx.HTTPStatusError("rate limited", request=request, response=response)
    result = classify_error(exc, context="groq")
    assert result.category == ErrorCategory.RATE_LIMIT
    assert result.severity == ErrorSeverity.LOW
    assert result.should_retry is True
    assert result.should_alert is False
    assert result.should_disable_scraper is False


def test_401_auth():
    request = httpx.Request("GET", "http://test.com")
    response = httpx.Response(401, request=request)
    exc = httpx.HTTPStatusError("unauthorized", request=request, response=response)
    result = classify_error(exc, context="api")
    assert result.category == ErrorCategory.AUTH
    assert result.severity == ErrorSeverity.CRITICAL
    assert result.should_retry is False
    assert result.should_alert is True
    assert result.should_disable_scraper is True


def test_403_forbidden():
    request = httpx.Request("GET", "http://test.com")
    response = httpx.Response(403, request=request)
    exc = httpx.HTTPStatusError("forbidden", request=request, response=response)
    result = classify_error(exc, context="api")
    assert result.category == ErrorCategory.AUTH
    assert result.should_disable_scraper is True


def test_404_not_found():
    request = httpx.Request("GET", "http://test.com")
    response = httpx.Response(404, request=request)
    exc = httpx.HTTPStatusError("not found", request=request, response=response)
    result = classify_error(exc, context="url")
    assert result.category == ErrorCategory.NOT_FOUND
    assert result.should_retry is False
    assert result.should_alert is True


def test_500_server_error():
    request = httpx.Request("GET", "http://test.com")
    response = httpx.Response(500, request=request)
    exc = httpx.HTTPStatusError("internal error", request=request, response=response)
    result = classify_error(exc, context="store")
    assert result.category == ErrorCategory.SERVER_ERROR
    assert result.should_retry is True
    assert result.should_alert is True


def test_503_server_error():
    request = httpx.Request("GET", "http://test.com")
    response = httpx.Response(503, request=request)
    exc = httpx.HTTPStatusError("unavailable", request=request, response=response)
    result = classify_error(exc, context="store")
    assert result.category == ErrorCategory.SERVER_ERROR
    assert result.should_retry is True


def test_unknown_http_error():
    request = httpx.Request("GET", "http://test.com")
    response = httpx.Response(418, request=request)
    exc = httpx.HTTPStatusError("teapot", request=request, response=response)
    result = classify_error(exc, context="test")
    assert result.category == ErrorCategory.UNKNOWN
    assert result.should_retry is False


def test_unknown_exception():
    exc = ValueError("something went wrong")
    result = classify_error(exc)
    assert result.category == ErrorCategory.UNKNOWN
    assert result.should_retry is False


def test_ssl_error():
    exc = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    result = classify_error(exc, context="secure-store")
    assert result.category == ErrorCategory.NETWORK
    assert result.should_retry is True


def test_context_in_message():
    exc = httpx.TimeoutException("timeout")
    result = classify_error(exc, context="my_store")
    assert "my_store" in result.message
