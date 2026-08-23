# `review_queue_service` — API

> Última atualização: 2026-08-23 01:22 UTC
> Gerado por AST parsing dos serviços em `services/review_queue_service.py`.

## Funções Públicas (7)

### approve_review_item(item_id: str, ingredient_id: str, brand_override: str)

### auto_approve_high_confidence(threshold: float, limit: int | None, dry_run: bool)

Aprova automaticamente itens pendentes com confiança >= threshold.

### auto_reject_stale_review_items(max_age_days: int, min_confidence: float)

### get_review_queue(limit: int)

Retorna apenas itens PENDENTES (fix raiz: antes misturava approved/rejected).

### get_review_queue_pending_count()

Contagem real de pendentes (independente do limit da página).

### insert_review_item(item: ReviewItem)

### reject_review_item(item_id: str)

