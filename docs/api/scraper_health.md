# `scraper_health` — API

> Última atualização: 2026-07-05 19:08 UTC
> Gerado por AST parsing dos serviços em `services/scraper_health.py`.

## Funções Públicas (4)

### attempt_heal(scraper_name: str | None, dry_run: bool)

For every currently-disabled scraper older than MIN_IDLE_DAYS_BEFORE_HEAL
days, evaluate the latest scraping_logs and decide whether to reactivate.

### classify_error_for_alert(reason: str | None)

Coarse 1-line classifier used in alerting + scraper_health_log.error_class.

### record_failure(scraper_name: str, reason: str | None, items_found: int, products_matched: int, flyer_count: int, attempted_by: str)

Record a failure and auto-disable the scraper if THRESHOLD_FAILURES hit.

### record_success(scraper_name: str, items_found: int, products_matched: int, flyer_count: int, attempted_by: str)

Record a successful run; resets failure counter.

