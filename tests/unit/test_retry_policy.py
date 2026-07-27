import httpx
import pytest

from services.retry_policy import RetryDecision, RetryPolicy, get_policy, with_retry


def test_default_policy():
    p = get_policy()
    assert p.max_retries == 3
    assert p.base_delay == 1.0
    assert p.max_delay == 30.0


def test_aggressive_policy():
    p = get_policy("aggressive")
    assert p.max_retries == 6
    assert p.base_delay == 10.0


def test_llm_policy():
    p = get_policy("llm")
    assert p.max_retries == 2


def test_should_retry_timeout():
    p = RetryPolicy()
    exc = httpx.TimeoutException("timeout")
    assert p.should_retry(exc, 0) == RetryDecision.RETRY
    assert p.should_retry(exc, 2) == RetryDecision.RETRY
    assert p.should_retry(exc, 3) == RetryDecision.ABORT


def test_should_retry_connect_error():
    p = RetryPolicy()
    exc = httpx.ConnectError("connection refused")
    assert p.should_retry(exc, 0) == RetryDecision.RETRY


def test_should_retry_network_error():
    p = RetryPolicy()
    exc = httpx.NetworkError("network unreachable")
    assert p.should_retry(exc, 0) == RetryDecision.RETRY


def test_should_retry_429():
    p = RetryPolicy()
    request = httpx.Request("GET", "http://test.com")
    response = httpx.Response(429, request=request)
    exc = httpx.HTTPStatusError("rate limited", request=request, response=response)
    assert p.should_retry(exc, 0) == RetryDecision.RETRY


def test_should_retry_500():
    p = RetryPolicy()
    request = httpx.Request("GET", "http://test.com")
    response = httpx.Response(500, request=request)
    exc = httpx.HTTPStatusError("server error", request=request, response=response)
    assert p.should_retry(exc, 0) == RetryDecision.RETRY


def test_should_not_retry_404():
    p = RetryPolicy()
    request = httpx.Request("GET", "http://test.com")
    response = httpx.Response(404, request=request)
    exc = httpx.HTTPStatusError("not found", request=request, response=response)
    assert p.should_retry(exc, 0) == RetryDecision.ABORT


def test_should_not_retry_403():
    p = RetryPolicy()
    request = httpx.Request("GET", "http://test.com")
    response = httpx.Response(403, request=request)
    exc = httpx.HTTPStatusError("forbidden", request=request, response=response)
    assert p.should_retry(exc, 0) == RetryDecision.ABORT


def test_get_delay_exponential():
    p = RetryPolicy(base_delay=1.0, jitter=False)
    assert p.get_delay(0) == 1.0
    assert p.get_delay(1) == 2.0
    assert p.get_delay(2) == 4.0


def test_get_delay_capped():
    p = RetryPolicy(base_delay=1.0, max_delay=5.0, jitter=False)
    assert p.get_delay(10) == 5.0


def test_get_delay_respects_retry_after():
    p = RetryPolicy(jitter=False)
    assert p.get_delay(0, retry_after=30) == 30.0


def test_get_delay_with_jitter():
    p = RetryPolicy(base_delay=1.0, jitter=True)
    delays = [p.get_delay(0) for _ in range(50)]
    assert all(0.5 <= d <= 1.0 for d in delays)


def test_classify_timeout():
    p = RetryPolicy()
    exc = httpx.TimeoutException("timeout")
    assert p.classify(exc).value == "timeout"


def test_classify_429():
    p = RetryPolicy()
    request = httpx.Request("GET", "http://test.com")
    response = httpx.Response(429, request=request)
    exc = httpx.HTTPStatusError("rate limited", request=request, response=response)
    assert p.classify(exc).value == "rate_limited"


def test_classify_500():
    p = RetryPolicy()
    request = httpx.Request("GET", "http://test.com")
    response = httpx.Response(500, request=request)
    exc = httpx.HTTPStatusError("server error", request=request, response=response)
    assert p.classify(exc).value == "server_error"


def test_with_retry_success():
    p = RetryPolicy(max_retries=3)
    called = 0

    def fn():
        nonlocal called
        called += 1
        return 42

    wrapped = with_retry(fn, policy=p)
    assert wrapped() == 42
    assert called == 1


def test_with_retry_eventual_success():
    p = RetryPolicy(max_retries=3, jitter=False)
    called = 0

    def fn():
        nonlocal called
        called += 1
        if called < 3:
            raise httpx.TimeoutException("timeout")
        return "ok"

    wrapped = with_retry(fn, policy=p)
    assert wrapped() == "ok"
    assert called == 3


def test_with_retry_exhausted():
    p = RetryPolicy(max_retries=2, jitter=False)
    called = 0

    def fn():
        nonlocal called
        called += 1
        raise httpx.TimeoutException("always fails")

    wrapped = with_retry(fn, policy=p)
    with pytest.raises(httpx.TimeoutException):
        wrapped()
    assert called == 2


def test_with_retry_non_retryable_abort():
    p = RetryPolicy(max_retries=3)
    called = 0

    def fn():
        nonlocal called
        called += 1
        request = httpx.Request("GET", "http://test.com")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    wrapped = with_retry(fn, policy=p)
    with pytest.raises(httpx.HTTPStatusError):
        wrapped()
    assert called == 1
