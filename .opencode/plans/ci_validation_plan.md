# Plano de Validação de CI — workflows disparados no fechamento do Sprint 18

> **Contexto**: fechamento Sprint 18 — após a reconciliação YAML↔DB (PR #79, merge `30ace99`),
> os fixes de infra do Store Recovery Test (PR #80 OCR PIL, PR #81 tesseract-por, PR #82/83
> dreno de queue) e o scraper com `--force` por último. Todos os workflows dispatching
> foram disparados um a um e monitorados até o status FINAL (regra #12).

## Resultado final (17/08/2026)

| Workflow | Archive | Rodou | Run | Result |
|----------|---------|-------|-----|--------|
| CI - Testes e Qualidade | `ci.yml` | PR #80/81/82/83 + master | 33285016525, 33287353077, 33288682115, 33331011455 | success |
| Teste_Full_Manual | `teste_full_manual.yml` | sessão anterior (pós reconciliação) | 33217252374 | success |
| E2E - Teste Completo | `e2e.yml` | pós #79 | 33225929022 | success |
| Dependency Audit | `dependency-audit.yml` | pós #79 | 33225930190 | success |
| CI - E2E Smoke Only | `ci-e2e-only.yml` | pós #79 | 33226458822 | success |
| sanitize-check | `sanitize-check.yml` | rerun sequencial | 33231411097 | success |
| Skills Maintenance | `skills-maintenance.yml` | rerun sequencial | 33231521930 | success |
| Store Recovery Test | `test_store_recovery.yml` | sequência de corridas | ##13 33231625239 FAIL → ##17 33331476932 **SUCCESS** | success (final) |
| On Demand Scrape (`--force`) | `on_demand_scrape.yml` → `scrape-reusable` | **último** | 33331866993 | success |
| Heal Scrapers | `heal-scrapers.yml` | — | — | cron-only (422 sem workflow_dispatch) |
| Backup - Restore Test | `backup.yml` + `restore-test.yml` | — | — | cron-only (422 sem workflow_dispatch) |
| Scrape (`scrape.yml`) | `scrape-reusable` | — | — | reusable (roda dentro do On Demand) |

## Cadeia de fix do Store Recovery Test (Atacadão) — 3 camadas de causa raiz

1. **OCR nunca rodava** (`cannot identify image file`): `img.tobytes()` é o pixel buffer cru,
   `Image.open` não identifica formato → salvar como PNG antes do preprocess. PR #80.
   Regression: `tests/unit/test_ocr.py`.
2. **Runner sem `por.traineddata`**: `test_store_recovery.yml` instalava `tesseract-ocr` sem
   `tesseract-ocr-por` (os outros workflows tinham) → OCR levanta run-time em pt-BR. PR #81. Lição #120.
3. **Deadlock `mp.Queue`**: filho `q.put(thumbnail)` sem leitor no pai → primeira versão do dreno
   (one-shot 15s, PR #82) foi insuficiente — filho `put` aos ~46s (download+OCR); versão final
   loopa até `p.is_alive()` (PR #83). Regressions: `test_collector_isolation.py` (big + delayed).
   Lições #121/#122.

Master CI green em todos os merges. On Demand Scrape (force) rodou por último, success.