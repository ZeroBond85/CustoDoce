from __future__ import annotations

from enum import Enum

import httpx


class ErrorCategory(Enum):
    NETWORK = "network"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    NOT_FOUND = "not_found"
    SERVER_ERROR = "server_error"
    PARSE = "parse"
    DNS = "dns"
    SSL = "ssl"
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ClassifiedError:
    def __init__(
        self,
        category: ErrorCategory,
        severity: ErrorSeverity,
        exception: Exception,
        message: str = "",
        should_retry: bool = False,
        should_alert: bool = False,
        should_disable_scraper: bool = False,
    ):
        self.category = category
        self.severity = severity
        self.exception = exception
        self.message = message or str(exception)
        self.should_retry = should_retry
        self.should_alert = should_alert
        self.should_disable_scraper = should_disable_scraper


def classify_error(exception: Exception, context: str = "") -> ClassifiedError:
    if isinstance(exception, httpx.ConnectError):
        err_str = str(exception).lower()
        if "getaddrinfo" in err_str or "dns" in err_str:
            return ClassifiedError(
                category=ErrorCategory.DNS,
                severity=ErrorSeverity.MEDIUM,
                exception=exception,
                message=f"DNS resolution failed for {context}",
                should_retry=True,
                should_alert=False,
                should_disable_scraper=False,
            )
        return ClassifiedError(
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.MEDIUM,
            exception=exception,
            message=f"Connection failed for {context}",
            should_retry=True,
            should_alert=False,
            should_disable_scraper=False,
        )

    if isinstance(exception, httpx.TimeoutException):
        return ClassifiedError(
            category=ErrorCategory.TIMEOUT,
            severity=ErrorSeverity.MEDIUM,
            exception=exception,
            message=f"Timeout for {context}",
            should_retry=True,
            should_alert=False,
            should_disable_scraper=False,
        )

    if isinstance(exception, httpx.NetworkError):
        return ClassifiedError(
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            exception=exception,
            message=f"Network error for {context}",
            should_retry=True,
            should_alert=True,
            should_disable_scraper=False,
        )

    if isinstance(exception, httpx.RemoteProtocolError):
        return ClassifiedError(
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.MEDIUM,
            exception=exception,
            message=f"Protocol error for {context}",
            should_retry=True,
            should_alert=False,
            should_disable_scraper=False,
        )

    if isinstance(exception, httpx.HTTPStatusError):
        status = exception.response.status_code
        if status == 429:
            return ClassifiedError(
                category=ErrorCategory.RATE_LIMIT,
                severity=ErrorSeverity.LOW,
                exception=exception,
                message=f"Rate limited ({status}) for {context}",
                should_retry=True,
                should_alert=False,
                should_disable_scraper=False,
            )
        if status in (401, 403):
            return ClassifiedError(
                category=ErrorCategory.AUTH,
                severity=ErrorSeverity.CRITICAL,
                exception=exception,
                message=f"Auth error ({status}) for {context}",
                should_retry=False,
                should_alert=True,
                should_disable_scraper=True,
            )
        if status == 404:
            return ClassifiedError(
                category=ErrorCategory.NOT_FOUND,
                severity=ErrorSeverity.LOW,
                exception=exception,
                message=f"Not found ({status}) for {context}",
                should_retry=False,
                should_alert=True,
                should_disable_scraper=False,
            )
        if status >= 500:
            return ClassifiedError(
                category=ErrorCategory.SERVER_ERROR,
                severity=ErrorSeverity.HIGH,
                exception=exception,
                message=f"Server error ({status}) for {context}",
                should_retry=True,
                should_alert=True,
                should_disable_scraper=False,
            )
        return ClassifiedError(
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.MEDIUM,
            exception=exception,
            message=f"HTTP {status} for {context}",
            should_retry=False,
            should_alert=True,
            should_disable_scraper=False,
        )

    return ClassifiedError(
        category=ErrorCategory.UNKNOWN,
        severity=ErrorSeverity.MEDIUM,
        exception=exception,
        message=str(exception),
        should_retry=False,
        should_alert=True,
        should_disable_scraper=False,
    )
