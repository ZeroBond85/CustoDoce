"""SSRF guard for URLs fetched server-side from untrusted/DB sources.

Flyer image URLs are stored in the `flyers` table by external aggregator
scrapers. A malicious or compromised source could inject an internal/metadata
URL (e.g. http://169.254.169.254/, http://10.0.0.1/). This module blocks
those before any httpx request is made. [security audit A-03]

Defense-in-depth (per 2026 SSRF best practices: OWASP, safeguard.sh,
httpx-secure, duckduckgo-mcp):

1. Scheme allowlist (http/https only) — blocks file://, gopher://, dict://.
2. Explicit domain allowlist — only known public e-commerce/aggregator hosts
   may be fetched. Arbitrary domains are rejected regardless of scheme.
3. DNS resolution + public-IP check — hosts are resolved and every resolved
   address must be globally routable (defeats DNS rebinding / TOCTOU and
   internal IPs hidden behind an allowlisted-looking domain).
4. Dangerous network blocks — RFC1918, loopback, link-local (incl. cloud
   metadata 169.254.169.254 and 169.254.170.2), CGNAT 100.64.0.0/10,
   NAT64 64:ff9b::/96, 6to4 2002::/16, multicast, reserved, IPv6 ULA/link-local.
5. Per-redirect re-validation — `make_safe_client()` injects an httpx event
   hook that runs every redirect hop back through the guard (CVE-2026-35459
   class of bug).

http (non-TLS) is permitted for allowlisted hosts only (many flyer images are
served over http). The public-IP check still applies.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.parse

# Domains that are legitimate flyer/image hosts. Expand as needed.
# These are PUBLIC e-commerce/aggregator hosts whose images we fetch server-side.
_ALLOWED_SUFFIXES: tuple[str, ...] = (
    "assai.com.br",
    "atacadao.com.br",
    "atacadao.encarte.br.com",
    "tendaatacado.com.br",
    "roldao.com.br",
    "blog.roldao.com.br",
    "samsclub.com.br",
    "makro.com.br",
    "maxatacadista.com.br",
    "supermuffato.com.br",
    "carrefour.com.br",
    "mercado.carrefour.com.br",
    "extra.com.br",
    "folheteria.clubeextra.com.br",
    "paodeacucar.com.br",
    "viavarejo.com.br",
    "gigafarma.com.br",
    "giga.com.vc",
    "gigavc.vtexassets.com",
    "vtexassets.com",
    "vtexcommercestable.com.br",
    "tiendeo.com.br",
    "guiato.com.br",
    "promotons.com.br",
    "kimbino.com.br",
    "kimbicdn.com",
    "na.kimbicdn.com",
    "leafletscdn.com",
    "na.leafletscdn.com",
    "portafolhetos.com.br",
    "facebook.com",
    "fbcdn.net",
    "cloudfront.net",
    "supabase.co",
    "supabase.in",
)

_BLOCKED_HOST_KEYWORDS = ("169.254.169.254", "metadata", "localhost", "internal")

# Dangerous networks (IPv4 + IPv6) that must never be reachable.
_DANGEROUS_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("0.0.0.0/8"),          # "this" network
    ipaddress.ip_network("10.0.0.0/8"),         # RFC1918 private
    ipaddress.ip_network("100.64.0.0/10"),      # CGNAT (Aliyun metadata 100.100.100.200)
    ipaddress.ip_network("127.0.0.0/8"),        # loopback
    ipaddress.ip_network("169.254.0.0/16"),     # link-local (AWS metadata 169.254.169.254)
    ipaddress.ip_network("169.254.170.2/32"),   # AWS ECS task credentials
    ipaddress.ip_network("172.16.0.0/12"),      # RFC1918 private
    ipaddress.ip_network("192.0.0.0/24"),       # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1
    ipaddress.ip_network("192.88.99.0/24"),     # 6to4 relay anycast
    ipaddress.ip_network("192.168.0.0/16"),     # RFC1918 private
    ipaddress.ip_network("198.18.0.0/15"),      # benchmark
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),        # multicast
    ipaddress.ip_network("240.0.0.0/4"),        # reserved
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("64:ff9b::/96"),       # NAT64 (reaches IPv4 metadata)
    ipaddress.ip_network("2002::/16"),          # 6to4 (embedded IPv4)
    ipaddress.ip_network("fc00::/7"),           # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
]


def _is_allowlisted(host: str) -> bool:
    return any(host == s or host.endswith("." + s) for s in _ALLOWED_SUFFIXES)


def _ip_is_dangerous(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if not ip.is_global:
        return True
    return any(ip.version == net.version and ip in net for net in _DANGEROUS_NETWORKS)


def resolve_public_ips(host: str) -> list[str]:
    """Resolve a hostname to its public IPv4/IPv6 addresses.

    Raises ValueError if resolution fails or any resolved address is dangerous
    (private/loopback/link-local/reserved/NAT64/6to4/CGNAT/metadata).
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        raise ValueError(f"DNS resolution failed for {host!r}: {exc}") from exc
    ips: list[str] = []
    for info in infos:
        addr = str(info[4][0])
        # Strip IPv6 scope id if present.
        addr = addr.split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _ip_is_dangerous(ip):
            raise ValueError(f"Host {host!r} resolves to dangerous address {ip}")
        ips.append(addr)
    if not ips:
        raise ValueError(f"Host {host!r} resolved to no usable addresses")
    return ips


def is_safe_url(url: str, *, allow_http: bool = False) -> bool:
    """Return True only if the URL is safe to fetch.

    Checks: valid absolute URL, http/https scheme, host on the domain allowlist,
    and (for non-literal hosts) that DNS resolution yields only globally-routable
    addresses. http is permitted for allowlisted hosts only.
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

    host = (parsed.hostname or "").lower()
    if not host:
        return False

    if any(kw in host for kw in _BLOCKED_HOST_KEYWORDS):
        return False

    host_allowed = _is_allowlisted(host)

    # http permitted only for allowlisted hosts (or explicit opt-in).
    if scheme == "http" and not allow_http and not host_allowed:
        return False

    # Literal IP: check directly.
    try:
        ip = ipaddress.ip_address(host)
        return not _ip_is_dangerous(ip)
    except ValueError:
        pass

    # Domain host: require allowlist + safe DNS resolution.
    if not host_allowed:
        return False
    try:
        resolve_public_ips(host)
    except ValueError:
        return False
    return True


def guard_url(url: str, *, allow_http: bool = False) -> str | None:
    """Return the URL if safe, else None (caller should skip the fetch)."""
    return url if is_safe_url(url, allow_http=allow_http) else None


def validate_redirect_target(url: str) -> None:
    """Raise httpx.UnsupportedProtocol if a redirect target is not SSRF-safe.

    Mirrors is_safe_url but raises instead of returning bool, for use inside an
    httpx response event hook (re-validates every redirect hop — CVE-2026-35459).
    """
    import httpx

    if is_safe_url(url):
        return
    raise httpx.UnsupportedProtocol(f"SSRF guard: blocked redirect to {url}")


def make_safe_client(**client_kwargs) -> object:
    """Build an httpx.Client that re-validates every redirect hop (SSRF-safe).

    Usage::

        from services.url_guard import make_safe_client
        client = make_safe_client(timeout=40.0, follow_redirects=True)
        client.get(image_url)  # each redirect re-checked against is_safe_url

    The event hook inspects the redirect target host and rejects it (by raising)
    if it is not allowlisted / publicly routable, closing the CVE-2026-35459
    class of redirect-based SSRF.
    """
    import httpx

    def _on_response(response: httpx.Response) -> None:
        if response.next_request is None:
            return
        validate_redirect_target(str(response.next_request.url))

    client_kwargs.setdefault("event_hooks", {})
    hooks = client_kwargs["event_hooks"]
    existing = hooks.get("response") or []

    def _hook(resp: httpx.Response) -> None:
        for h in existing:
            h(resp)
        _on_response(resp)

    hooks["response"] = [_hook]
    return httpx.Client(**client_kwargs)


__all__ = [
    "is_safe_url",
    "guard_url",
    "resolve_public_ips",
    "make_safe_client",
    "validate_redirect_target",
]
