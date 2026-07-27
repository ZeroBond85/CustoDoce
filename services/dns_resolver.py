from __future__ import annotations

import socket
import time
from urllib.parse import urlparse

from services.logger import logger


def resolve_hostname(hostname: str, max_retries: int = 3, delay: float = 2.0) -> list[str] | None:
    """Resolve a hostname to IP addresses with retry.

    Returns list of IP strings, or None if resolution failed after all retries.
    """
    for attempt in range(max_retries):
        try:
            infos = socket.getaddrinfo(hostname, None)
            ips = list({info[4][0].split("%", 1)[0] for info in infos})
            if ips:
                return ips
        except (socket.gaierror, UnicodeError, OSError) as e:
            logger.warning("DNS resolve attempt %d/%d for %s: %s", attempt + 1, max_retries, hostname, e)
            if attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))
    return None


def check_url_reachable(url: str, max_retries: int = 3) -> bool:
    """Check if a URL's hostname is resolvable via DNS (with retry).

    Does NOT make an HTTP request — only checks DNS resolution.
    Use this before fetch to fail fast on DNS issues.
    """
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return False
        ips = resolve_hostname(hostname, max_retries=max_retries)
        return ips is not None and len(ips) > 0
    except Exception:
        return False
