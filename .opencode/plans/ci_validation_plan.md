# Plano de Validação de CI — workflows não disparados (pós-merge #79)

> **Contexto**: merge da reconciliação YAML↔DB (PR #79 → `master`, commit `30ace99`).
> Mudança: `config/ingredients.yaml` (regenerado do DB) + `LESSONS.md` + `AGENTS.md` (sync).
> Sem alteração de lógica de código, sem alteração de dependências.

## Status dos workflows de VALIDAÇÃO (todos ✅ para este change)

| Workflow | Arquivo | Trigger | Rodou p/ #79 | Run | Result |
|----------|---------|---------|--------------|-----|--------|
| CI - Testes e Qualidade | `ci.yml` | push/PR | ✅ PR + master | 33224869009 / 33225278324 | success |
| Teste_Full_Manual | `teste_full_manual.yml` | dispatch | ✅ (sessão anterior) | 33217252374 | success |
| E2E - Teste Completo | `e2e.yml` | cron(1º)+dispatch | ✅ | 33225929022 | success |
| Dependency Audit | `dependency-audit.yml` | cron(1º)+dispatch | ✅ | 33225930190 | success |
| CI - E2E Smoke Only | `ci-e2e-only.yml` | dispatch | ✅ | 33226458822 | success |

> Observação: `Teste_Full_Manual` 33217252374 rodou ANTES do merge da reconciliação, mas cobre todo o path (e2e-full/real/visual/diagnostics/deploy-check). O `E2E - Teste Completo` 33225929022 rodou APÓS o merge e valida o dashboard D5 (YAML=27) no master atual. Ambos green.

## Workflows NÃO disparados (lista para validação manual)

Estes são **operacionais/agendados** — NÃO validam a mudança de `ingredients.yaml` (config/doc).
Rodam automaticamente por cron. Dispará-los manualmente consome quota de scrape / faz
restore de backup / roda manutenção — use só para validar INFRA, não o change.

| Workflow | Arquivo | Trigger (cron) | Recomendação p/ #79 |
|----------|---------|----------------|---------------------|
| Scrape | `scrape.yml` (+`scrape-reusable.yml`) | 2x/dia (00:00/12:00 UTC) | ❌ Não rodar (queima quota) — roda sózinho |
| On Demand Scrape | `on_demand_scrape.yml` | dispatch | ❌ Não rodar (scrape real) |
| Heal Scrapers | `heal-scrapers.yml` | mensal (dia 1) | ⚠️ Opcional (infra) |
| Backup - Restore Test | `backup.yml` + `restore-test.yml` | semanal | ⚠️ Opcional (infra) |
| sanitize-check | `sanitize-check.yml` | semanal | ⚠️ Opcional (infra) |
| Store Recovery Test | `test_store_recovery.yml` | teste | ⚠️ Opcional (infra) |
| Skills Maintenance | `skills-maintenance.yml` | mensal (dia 1) | ⚠️ Opcional (infra) |

## Comandos para disparar (sob demanda, validação de INFRA)

```bash
# Via WSL (gh autenticado):
gh workflow run "Scrape" --ref master
gh workflow run "On Demand Scrape" --ref master
gh workflow run "Heal Scrapers" --ref master
gh workflow run "Backup - Restore Test" --ref master
gh workflow run "sanitize-check" --ref master
gh workflow run "Store Recovery Test" --ref master
gh workflow run "Skills Maintenance" --ref master
```

### Critérios de aceite (qualquer um dos acima, se rodado)
- `gh run view <id> --json conclusion` → `"success"`.
- Sem job `failure`/`cancelled` (exceto cancelamento intencional por concorrência).

## Conclusão
Para a mudança de config/doc do PR #79, **toda a suíte de validação de código está verde**
(ci.yml, Teste_Full_Manual, E2E - Teste Completo, Dependency Audit, CI - E2E Smoke Only).
Os workflows restantes são operacionais por cron e não precisam ser disparados manualmente
para este change — listados acima apenas para validação de infra, se desejado.
