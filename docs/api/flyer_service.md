# `flyer_service` — API

> Última atualização: 2026-07-21 01:33 UTC
> Gerado por AST parsing dos serviços em `services/flyer_service.py`.

## Funções Públicas (9)

### cleanup_non_food_flyers()

Deleta flyers de lojas nao-alimenticias (ex: Boticario, Magazine).

### cleanup_old_flyers(retention_days: int)

Deleta flyers com OCR failed mais antigos que retention_days.

### delete_flyer(flyer_id: str)

Delete a flyer by ID.

### get_flyer_detail(flyer_id: str)

Get detailed flyer information by ID.

### get_pending_flyers(limit: int)

### get_recent_flyers(days: int, source: str | None)

### mark_failed(flyer_id: str)

### mark_processed(flyer_id: str, products_count: int)

### upsert_flyer(flyer: dict)

