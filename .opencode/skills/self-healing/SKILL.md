---
name: self-healing
description: "Scraper self-healing: record_failure/success(), attempt_heal(), classify_error_for_alert — regra obrigatória AGENTS.md lição #15"
---
# self-healing

Self-healing patterns para scrapers do CustoDoce. Implementação em `services/scraper_health.py`.

**Regra obrigatória (AGENTS.md lição #15):** TODO scraper DEVE chamar `record_failure`/`record_success`.

## API Real

```python
from services.scraper_health import (
    record_failure, record_success, attempt_heal, classify_error_for_alert
)

# Registra falha (auto-disables after THRESHOLD_FAILURES=3 consecutives)
result = record_failure(
    scraper_name="extra_flyer",
    reason="Timeout ao baixar PDF",
    items_found=0,
    products_matched=0,
    flyer_count=1,
    attempted_by="scrape_all",
)
# result → {"recorded": True, "scraper": "extra_flyer", "failures_count": 1,
#            "auto_disabled": False, "error_class": "Timeout"}

# Registra sucesso (reseta contador de falhas)
result = record_success(
    scraper_name="extra_flyer",
    items_found=15,
    products_matched=12,
    flyer_count=1,
    attempted_by="scrape_all",
)
# result → {"recorded": True, "scraper": "extra_flyer"}

# Heal automático (cron 15 dias, via heal-scrapers.yml)
summary = attempt_heal(scraper_name=None, dry_run=False)
# summary → {"candidates": [...], "reactivated": [...], "skipped": [...], "missing_facts": [...]}

# Classifica erro para alerta
error_class = classify_error_for_alert("SSL certificate expired")
# → "SSLError"
```

## Classificação de Erros

`classify_error_for_alert(reason)` mapeia string de erro para categoria:

| Categoria | Match |
|-----------|-------|
| `Timeout` | timeout, timed out |
| `SSLError` | ssl, tls, certificate |
| `ConnectError` | connect, connection |
| `LayoutChanged` | 404, not found, parse, selector, no element |
| `AntiBot` | captcha, robot |
| `RateLimit` | rate, 429, too many |
| `ProxyConfigError` | proxy |
| `Other` | default |
| `Unknown` | reason=None |

## Auto-Disable Rules

```python
# THRESHOLD_FAILURES = 3 (configurável via env SCRAPER_HEALTH_THRESHOLD)
# Ao atingir: store.is_active = False + evento auto_disabled logado

record_failure("loja_x", reason="404")  # failure 1
record_failure("loja_x", reason="404")  # failure 2
record_failure("loja_x", reason="404")  # failure 3 → auto-disabled!
```

## Auto-Enable (Heal)

Cron 15 dias (`heal-scrapers.yml`) chama `attempt_heal()`:
1. Lista stores com `is_active = False`
2. Filtra as que estão `MIN_IDLE_DAYS_BEFORE_HEAL = 15` dias paradas
3. Verifica se há logs de sucesso recentes
4. Se critérios ok → reativa (salvo dry_run)

## Thresholds Configuráveis

| Env var | Default | Descrição |
|---------|---------|-----------|
| `SCRAPER_HEALTH_THRESHOLD` | 3 | Falhas consecutivas antes de auto-disable |
| `SCRAPER_HEALTH_RECOVERY_ITEMS` | 1 | Mínimo de itens para considerar recuperação |
| `SCRAPER_HEALTH_HEAL_DAYS` | 15 | Dias parado antes de tentar heal |

## Integration with GitHub Actions

```yaml
# heal-scrapers.yml (cron 15d)
- name: Heal disabled scrapers
  run: python scripts/heal_scrapers.py run-all --dry-run
```

## Antipatterns

- ❌ Não chamar `record_failure/success()` em todo scraper
- ❌ Silently swallow exceptions sem logar
- ❌ Usar `auto_reable()`, `try_reenable()` ou `get_health()` — **não existem no código**
- ❌ Ignorar o return dict de `record_failure` (tem `auto_disabled` flag)
- ❌ Não tratar o fallback `{"recorded": False}` quando Supabase está offline

## Scripts

```bash
# Listar desabilitados
python scripts/heal_scrapers.py list-disabled

# Tentar re-enable
python scripts/heal_scrapers.py run-all --dry-run

# Ver estatísticas
python scripts/heal_scrapers.py failures "<store>" --days 30
```

## Dashboard

O dashboard `dashboard/pages/scraper_health.py` mostra status atual de todos scrapers, histórico de failures e tendências de health.
