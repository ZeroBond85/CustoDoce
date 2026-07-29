# `selector_resolver` — API

> Última atualização: 2026-07-29 15:35 UTC
> Gerado por AST parsing dos serviços em `services/selector_resolver.py`.

## Funções Públicas (3)

### get_available_variants()

Return list of available selector variant names.

### reload()

Force reload of selectors.yaml on next call.

### resolve_selectors(store_config: dict)

Resolve selectors for a store: store-specific > type variant > defaults.

