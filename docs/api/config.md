# `config` — API

> Última atualização: 2026-07-19 13:59 UTC
> Gerado por AST parsing dos serviços em `services/config.py`.

## Funções Públicas (3)

### get(key: str, default)

### get_feature(path: str, ingredient: str, default)

Gets a feature flag. If an ingredient is provided, it checks for a
per-ingredient override in 'features.overrides[ingredient]'.

### reload()

