# `config_db` — API

> Última atualização: 2026-07-18 04:39 UTC
> Gerado por AST parsing dos serviços em `services/config_db.py`.

## Funções Públicas (32)

### add_alias_to_ingredient(canonical_name_or_id: str, new_alias: str)

### delete_alert_rule(rule_id: str)

### delete_ingredient(ingredient_id: str)

### delete_recipient(recipient_id: str)

### delete_schedule(schedule_id: str)

### delete_scrape_frequency(freq_id: str)

### delete_store(store_id: str)

### get_active_ingredients()

### get_active_recipients(channel: str | None)

### get_active_stores(tier: int | None, store_type: str | None)

### get_all_alert_rules(include_disabled: bool)

### get_all_feature_flags()

### get_all_ingredients(include_inactive: bool)

### get_all_recipients(include_inactive: bool)

### get_all_schedules(include_disabled: bool)

### get_all_stores(include_inactive: bool)

### get_enabled_alert_rules(trigger: str | None)

### get_enabled_schedules()

### get_feature_flag(key: str, default: bool)

### get_ingredient_by_id(ingredient_id: str)

### get_ingredient_by_name(canonical_name: str)

### get_scrape_frequency(store_id: str | None, tier: int | None)

### get_store_by_id(store_id: str)

### get_store_by_name(name: str)

### update_schedule_run(schedule_id: str, last_run: datetime, next_run: datetime | None)

### upsert_alert_rule(data: dict)

### upsert_feature_flag(key: str, enabled: bool, description: str)

### upsert_ingredient(data: dict[str, Any])

### upsert_recipient(data: dict)

### upsert_schedule(data: dict)

### upsert_scrape_frequency(data: dict)

### upsert_store(data: dict[str, Any])

