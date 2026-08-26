# `config` — API

> Última atualização: 2026-08-26 16:42 UTC
> Gerado por AST parsing dos serviços em `services/config.py`.

## Funções Públicas (3)

### get(key: str, default: Any)

### get_feature(path: str, ingredient: str | None, default: Any)

Gets a feature flag. If an ingredient is provided, it checks for a
per-ingredient override in 'features.overrides[ingredient]'.

### reload()

