# `llm_preflight` — API

> Última atualização: 2026-09-09 02:22 UTC
> Gerado por AST parsing dos serviços em `services/llm_preflight.py`.

## Funções Públicas (3)

### get_best_provider(providers: list[str] | None)

Retorna o primeiro provider saudável na ordem dada, ou None.

### llm_preflight(providers: list[str] | None, force: bool)

Roda preflight para provedores indicados. Retorna {provider: ok}.

### mark_deprecated(provider: str)

Marca manualmente um provedor como deprecated (ex.: ao receber 400/404 downstream).

