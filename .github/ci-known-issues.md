# CI Known Issues — Incidente 2026-08-17 (RESOLVIDO)

> **Status: RESOLVIDO.** Este documento registra o incidente de CI e as causas
> raiz para evitar recorrência. Não é mais uma lista de "flakiness aceitável".

## Sintoma
CI `CI - Testes e Qualidade` falhava em 3 frentes:
1. `docs-sync`: `[LIVE] README.md drift (badges/contadores)`
2. `unit` / `integration`: `ModuleNotFoundError: No module named 'supabase'/'dotenv'/'rapidfuzz'/'selectolax'/'structlog'/'curl_cffi'/'joblib'/'numpy'`
3. `e2e-smoke`: `net::ERR_CONNECTION_REFUSED at http://localhost:8501/`

## Causa raiz única (GAP local ↔ CI)
Os testes locais (WSL) têm TODAS as deps instaladas globalmente, então
`ModuleNotFoundError` **nunca se reproduzia localmente**. O CI instala apenas
`requirements-test.lock`, que estava **incompleto**: foi gerado só a partir de
`requirements-test.in`, nunca com o comando canônico combinado (test+dev+prod).

Consequências:
- Faltavam deps de produção no test lock → `ModuleNotFoundError` no CI.
- `numpy`/`python-telegram-bot` ausentes → módulos de teste (`test_semantic_matcher`,
  `test_telegram_handlers`) falhavam ao importar → `pytest --collect-only` coletava
  menos testes → badge do README (contagem) divergia → drift no docs-sync.
- `dependency-audit.yml` só dispara em PR ou cron mensal; os commits de correção
  foram diretos no master → a validação de lock nunca rodou.

## Correções aplicadas
- **Phase 1**: regenerados os 4 lock files com o comando canônico em WSL/Linux
  (`scripts/regen_locks.sh`). `requirements-test.lock` agora 629 linhas (era 181) e
  contém numpy, pandas, pillow, openpyxl, optimum, transformers, python-telegram-bot.
- **Phase 3 (e2e-smoke)**:
  - `admin/app.py`: lazy-load das 21 páginas via closure (`_make_lazy_page`) →
    o startup só importa a página default, eliminando o "import storm" que estourava
    o warmup do CI.
  - `ci.yml`: probe de prontidão real (espera `"You can now view your Streamlit app"`
    no log e falha o step se não subir) + `tests/e2e/test_e2e_smoke_basic.py` com
    retry em `page.goto` (connection refused).
- **Phase 4 (flaky test)**: `test_approve_duplicate_price_no_23505` agora usa
  `store_id` único por run (uuid) → unique key `(ingredient, store, date)` nunca
  colide entre runs concorrentes (causa raiz do 23505). Monkeypatch de
  `add_alias_to_ingredient`/`upsert_ingredient` evita poluir ingrediente de
  produção. Band-aid `_skip_if_ci()` removido. Validado 3/3 local.

## Guardrails para não recorrer
1. `dependency-audit.yml` agora dispara em `push` para `master` (com `paths:` filter)
   além de PR/cron → valida o lock mesmo em push direto.
2. `scripts/check_environment_parity.py::_check_lock_superset`: afirma que
   `requirements-test.lock` é **superset** de `requirements-prod.lock`/`dev.lock`
   (detecta pacote AUSENTE, não só versão divergente) e que `requirements.lock` ==
   `requirements-test.lock`.
3. `scripts/regen_locks.sh`: comando canônico único — não rode pip-compile à mão.

## Validação local (se CI falhar de novo)
```bash
bash scripts/regen_locks.sh                 # regenera locks em WSL
python scripts/check_environment_parity.py  # supra-set check
python scripts/sync_docs.py --check --strict
pytest tests/unit/ tests/schema/ -q
pytest tests/integration/test_review_queue_e2e.py::TestApproveReviewItem -q
```
