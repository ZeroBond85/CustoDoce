# `url_guard` — API

> Última atualização: 2026-07-21 01:55 UTC
> Gerado por AST parsing dos serviços em `services/url_guard.py`.

## Funções Públicas (5)

### guard_url(url: str)

Return the URL if safe, else None (caller should skip the fetch).

### is_safe_url(url: str)

Return True only if the URL is safe to fetch.

### make_safe_client()

Build an httpx.Client that re-validates every redirect hop (SSRF-safe).

### resolve_public_ips(host: str)

Resolve a hostname to its public IPv4/IPv6 addresses.

### validate_redirect_target(url: str)

Raise httpx.UnsupportedProtocol if a redirect target is not SSRF-safe.

