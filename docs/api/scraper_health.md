# `scraper_health` — API

> Última atualização: 2026-07-22 22:03 UTC
> Gerado por AST parsing dos serviços em `services/scraper_health.py`.

## Funções Públicas (8)

### attempt_heal(scraper_name: str | None, dry_run: bool)

For every currently-disabled scraper older than MIN_IDLE_DAYS_BEFORE_HEAL
days, evaluate the latest scraping_logs and decide whether to reactivate.

### classify_error_for_alert(reason: str | None)

Coarse 1-line classifier used in alerting + scraper_health_log.error_class.

### compute_all_health_scores(health_data: list[dict])

Enrich a list of store health dicts with health_score + label.

### compute_health_score(data: dict)

Compute 0–100 health score for a single scraper from its metric dict.

### health_score_label(score: int)

Return text + emoji label for a 0–100 health score.

### record_failure(scraper_name: str, reason: str | None, items_found: int, products_matched: int, flyer_count: int, attempted_by: str)

Record a failure and auto-disable the scraper if THRESHOLD_FAILURES hit.

### record_success(scraper_name: str, items_found: int, products_matched: int, flyer_count: int, attempted_by: str)

Record a successful run; resets failure counter.

### record_transient_failure(scraper_name: str, error_class: str, reason: str | None, items_found: int, products_matched: int, flyer_count: int, attempted_by: str)

Registra falha TRANSITÓRIA (rede/timeout/rate-limit/recurso).

