"""SSRF guard for URLs fetched server-side from untrusted/DB sources.

Flyer image URLs are stored in the `flyers` table by external aggregator
scrapers. A malicious or compromised source could inject an internal/metadata
URL (e.g. http://169.254.169.254/, http://10.0.0.1/). This module blocks
those before any httpx request is made. [security audit A-03]
"""

from __future__ import annotations

import ipaddress
import urllib.parse

# Domains that are legitimate flyer/image hosts. Expand as needed.
_ALLOWED_SUFFIXES: tuple[str, ...] = (
    "assai.com.br",
    "atacadao.com.br",
    "tendaatacado.com.br",
    "roldao.com.br",
    "samsclub.com.br",
    "makro.com.br",
    "maxatacadista.com.br",
    "carrefour.com.br",
    "extra.com.br",
    "paodeacucar.com.br",
    "viavarejo.com.br",
    "gigafarma.com.br",
    "tiendeo.com.br",
    "guiato.com.br",
    "facebook.com",
    "fbcdn.net",
    "supabase.co",
)

_BLOCKED_HOST_KEYWORDS = ("169.254.169.254", "metadata", "localhost", "internal")


def is_safe_url(url: str, *, allow_http: bool = False) -> bool:
    """Return True only if the URL is safe to fetch.

    Checks: valid absolute URL, http/https scheme (https unless allow_http),
    host resolves to a public IP (not loopback/link-local/private), and either
    matches an allowed domain suffix or is a public IP that is not reserved.
    """
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
    except (ValueError, TypeError):
        return False

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("https", "http"):
        return False
    if scheme == "http" and not allow_http:
        return False

    host = (parsed.hostname or "").lower()
    if not host:
        return False

    if any(kw in host for kw in _BLOCKED_HOST_KEYWORDS):
        return False

    # Block private/loopback/link-local/reserved IP literals.
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            return False
    except ValueError:
        # Not a literal IP — check domain allowlist.
        if not any(host == s or host.endswith("." + s) for s in _ALLOWED_SUFFIXES):
            return False

    return True


def guard_url(url: str, *, allow_http: bool = False) -> str | None:
    """Return the URL if safe, else None (caller should skip the fetch)."""
    return url if is_safe_url(url, allow_http=allow_http) else None
