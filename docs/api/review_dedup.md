# `review_dedup` — API

> Última atualização: 2026-09-07 13:21 UTC
> Gerado por AST parsing dos serviços em `services/review_dedup.py`.

## Funções Públicas (2)

### find_pending_duplicates(raw_product: str, store_name: str, threshold: float, lookback_days: int)

Busca pending items na review_queue e verifica duplicata semântica.

### is_semantic_duplicate(new_product: str, existing_products: list[str], threshold: float)

Retorna top-1 similar se score >= threshold, senão None.

