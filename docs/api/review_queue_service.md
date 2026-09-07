# `review_queue_service` — API

> Última atualização: 2026-09-06 16:00 UTC
> Gerado por AST parsing dos serviços em `services/review_queue_service.py`.

## Funções Públicas (9)

### approve_review_item(item_id: str, ingredient_id: str, brand_override: str, feedback_decision: str)

Aprova item da review_queue: resolve ingredient/store, upsert price, auto-learning.

### auto_approve_high_confidence(threshold: float, limit: int | None, dry_run: bool)

Aprova automaticamente itens pendentes com confiança >= threshold.

### auto_approve_llm_confirmed(threshold: float, limit: int | None, dry_run: bool, llm_floor: float)

Aprova automaticamente itens pendentes em que o LLM confirma o candidato top-1.

### auto_reject_stale_review_items(max_age_days: int, min_confidence: float)

### get_review_queue(limit: int)

Retorna apenas itens PENDENTES (fix raiz: antes misturava approved/rejected).

### get_review_queue_pending_count()

Contagem real de pendentes (independente do limit da página).

### insert_review_item(item: ReviewItem)

### record_match_feedback(item: dict[str, Any], decision_type: str, decided_by: str, notes: str | None)

Grava uma decisão de match na tabela match_feedback (feedback loop).

### reject_review_item(item_id: str)

