from __future__ import annotations

import random
import time
from dataclasses import dataclass
from enum import Enum
from collections.abc import Callable

import httpx

from services.logger import logger


class RetryDecision(Enum):
    RETRY = "retry"
    FAIL_THROUGH = "fail_through"
    ABORT = "abort"


class RetryableError(Enum):
    TIMEOUT = "timeout"
    NETWORK = "network"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"


_NON_RETRYABLE_STATUSES = frozenset({400, 401, 403, 404, 405, 413, 422})  # noqa: S104


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: bool = True
    retryable_exceptions: tuple[type[Exception], ...] = (
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
    )

    def should_retry(self, exception: Exception, attempt: int) -> RetryDecision:
        if attempt >= self.max_retries:
            return RetryDecision.ABORT

        if isinstance(exception, httpx.TimeoutException):
            return RetryDecision.RETRY

        if isinstance(exception, (httpx.NetworkError, httpx.ConnectError, httpx.RemoteProtocolError)):
            return RetryDecision.RETRY

        if isinstance(exception, httpx.HTTPStatusError):
            status = exception.response.status_code
            if status in _NON_RETRYABLE_STATUSES:
                return RetryDecision.ABORT
            if status == 429:
                return RetryDecision.RETRY
            if status >= 500:
                return RetryDecision.RETRY
            return RetryDecision.ABORT

        return RetryDecision.FAIL_THROUGH

    def get_delay(self, attempt: int, retry_after: int | None = None) -> float:
        if retry_after is not None and retry_after > 0:
            return float(retry_after)
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)  # noqa: S311  # nosec B311
        return delay

    def classify(self, exception: Exception) -> RetryableError | None:
        if isinstance(exception, httpx.TimeoutException):
            return RetryableError.TIMEOUT
        if isinstance(exception, (httpx.NetworkError, httpx.ConnectError, httpx.RemoteProtocolError)):
            return RetryableError.NETWORK
        if isinstance(exception, httpx.HTTPStatusError):
            status = exception.response.status_code
            if status == 429:
                return RetryableError.RATE_LIMITED
            if status >= 500:
                return RetryableError.SERVER_ERROR
        return None


_POLICY_CACHE: dict[str, RetryPolicy] = {}


def get_policy(name: str = "default") -> RetryPolicy:
    if name not in _POLICY_CACHE:
        if name == "aggressive":
            _POLICY_CACHE[name] = RetryPolicy(max_retries=6, base_delay=10.0, max_delay=120.0)
        elif name == "llm":
            _POLICY_CACHE[name] = RetryPolicy(max_retries=2, base_delay=0.5, max_delay=5.0)
        else:
            _POLICY_CACHE[name] = RetryPolicy()
    return _POLICY_CACHE[name]


def with_retry(
    fn: Callable,
    policy: RetryPolicy | None = None,
    context: str = "",
    retryable_exceptions: tuple[type[Exception], ...] | None = None,
) -> Callable:
    policy = policy or get_policy()
    retryable = retryable_exceptions or policy.retryable_exceptions

    def wrapper(*args, **kwargs):
        last_exc = None
        for attempt in range(policy.max_retries):
            try:
                return fn(*args, **kwargs)
            except retryable as e:
                last_exc = e
                decision = policy.should_retry(e, attempt)
                if decision == RetryDecision.ABORT:
                    logger.warning("[%s] Abort retry after %d attempts: %s", context, attempt + 1, e)
                    raise
                delay = policy.get_delay(attempt)
                if attempt < policy.max_retries - 1:
                    logger.info("[%s] Retry %d/%d after %.1fs: %s", context, attempt + 1, policy.max_retries, delay, e)
                    time.sleep(delay)
            except Exception as e:
                last_exc = e
                decision = policy.should_retry(e, attempt)
                if decision != RetryDecision.RETRY:
                    raise
                delay = policy.get_delay(attempt)
                if attempt < policy.max_retries - 1:
                    time.sleep(delay)
        raise last_exc  # type: ignore[misc]
    return wrapper
