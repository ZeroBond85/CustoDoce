# Plano de Ação — `fix/zero-warn-scrapers`
**Objetivo:** Zero erros/warns em TODOS os scrapers, tiers 1/2a/3/4 coletando, motor de embeddings atualizado com acurácia decidida por benchmark (2 estágios) e validada na máquina real do GitHub.

---

## FASE 0 — Motor de embeddings (raiz do warning + acurácia)

### Diagnóstico comprovado
| Pacote | Lock atual | Realidade 2026 |
|---|---|---|
| `sentence-transformers` | 6.0.0 | exige `transformers>=5.0.0` |
| `transformers` | 5.15.0 (pin) | v5 remove `is_tf_available` |
| `optimum[onnxruntime]` | 1.17.1 (era-v4, sem upper bound) | quebra no v5 |
| `optimum-onnx` | — | **0.1.0 única no PyPI, exige `transformers<4.58`** |

→ **ST 6.0.0 + optimum-onnx = conflito insolúvel hoje.** ONNX quebra no CI (=warning) e roda fallback PyTorch. Decisão: **abandonar stack torch/transformers/optimum/ST → migrar para `fastembed 0.8.0`** (ONNX Runtime puro, sem torch, sem conflito de versão, mais rápido). WSL local já dessincronizado do lock (ST 5.7/optimum 2.1/onnx 1.28) → flag de parity.

### 0A — Benchmark de acurácia (WSL; hardware-independente)
- **Dataset rotulado real:** ~300 pares `(product_text, ingredient_id)` de `prices`/`review_queue` (positivos) + ~200 negativos de `store_registry`/não-matches; revisão manual de ~50 p/ rótulos limpos.
- **Candidatos** (fastembed, built-in ou `add_custom_model` fp32): `paraphrase-multilingual-MiniLM-L12-v2` (**baseline 2019**) · `paraphrase-multilingual-mpnet-base-v2` (278M) · `multilingual-e5-base` (~270M) · `multilingual-e5-large` (560M) · `bge-m3` (568M, **stretch** — `add_custom_model` se necessário).
- **Métricas:** accuracy@1 (ingr. correto top-1 entre 27), MRR, estabilidade do gate `combined=0.80` vs engine atual.
- **Saída:** `scripts/embedding_benchmark.py` → tabela comparativa. Decisão: melhor acurácia@1 pt-BR → **1-2 finalistas**.

### 0B — Validação na máquina real (runner GitHub)
- Workflow dedicado `embedding-benchmark.yml` (dispatch manual; não é gate de PR): roda **finalistas** em `ubuntu-latest` (2 vCPU / 7GB / budget 120min) e reporta: pico RSS, s/1000 emb, tempo/tamanho download, **extrapolação do scrape completo vs budget** com headroom p/ OCR/playwright.
- **Limites duros de decisão:**
  - Pico RSS ≤ **3.0 GB**
  - Tempo total embedding no scrape completo ≤ **20 min**
  - Latência média / 1000 embeddings ≤ **45 s**
- Se nenhum modelo passa → recuo p/ **`mpnet-multilingual`** (fallback seguro).
- **Decisão final = melhor acurácia que cabe na máquina medida.**

### 0C — Migração (após decisão)
- `requirements-prod.in`: drop `sentence-transformers`+`optimum[onnxruntime]`+drop `transformers==5.15.0`; add `fastembed>=0.8,<1.0`; `onnxruntime>=1.24.2,<2.0`. Regenerar **4 locks no WSL** (python3.14 nativo) + reinstalar WSL/`.venv314` + `check_environment_parity` verde.
- `parsers/semantic_matcher.py` (linhas 21-93): refactor p/ `TextEmbedding(model_name=<finalista>)` → `model.embed([text])` (np float32, sem pooling manual); remover `_ONNX_DIR`; **wipe `data/embedding_cache/*.npy` 1x**. Telemetria INFO de tempo de embedding no report.
- **Testes:** `test_semantic_matcher.py` (dim/corretude/determinismo), `tests/calibration/test_scoring_calibration.py`, regressão 0 warnings.

---

## FASE 1 — Tier 3 observável (Kimbino/Portafolhetos)
> Correção: `collect_aggregators_js` **não** está desabilitado (`False` = `needs_ing`, roda sem lista de ingredientes).
- `services/collector.py::_collect_flyers` (linha 983): adicionar `record_success(scraper_name, items_found, products_matched, flyer_count, attempted_by="collector")` no sucesso (hoje só `record_failure` no erro, 1043).
- Smoke local WSL `PlaywrightAggregatorScraper` p/ Kimbino + Portafolhetos: se 403/block → `curl_cffi` fallback (padrão Tiendeo já existente, collector 1164-1185).
- Tiendeo permanece `is_active=false` (403 sem proxy — decisão de infra documentada). Atacadão reativado no DB → confirmar coleta no force via OCR (tesseract-por #81).

---

## FASE 2 — Test pollution (preços + health log) — raiz
- **Causa raiz (confirmado via DB):** unit tests escrevem em **produção**. `test_collector_last_run_stats.py` mocka `log_scraper_run` (função errada), mas `_scrape_store` grava via `services.scraper_health.record_success()` → linhas `DeadStore/FakeStore/GeneralFlyerStore` (attempted_by=collector) no `scraper_health_log`.
- `tests/unit/conftest.py`: fixture **autouse** stubando `scraper_health.get_service_client` (raise) + `price_service.log_scraper_run` → nenhum unit test toca prod.
- `tests/integration/test_trigger.py` (232-331, Constraint Test Store/Hist Constraint Store/`_test_hist_unique_ing`): `try/finally` com cleanup em `prices`/`price_history` → **hermético**.
- Branch `fix/sanitize-test-data-sweep` (já tem 3 edits: `_TEST_STORES`, `_count_by_stores`, `_delete_by_stores`) **expandido:** +`_delete_test_health_rows()`; `sanitize-check.yml` (seg 12:00 UTC) passa a rodar `cleanup_price_fps --execute` + checagem de resíduo.

---

## FASE 3 — `prices.tier` consistente (fonte única)
- Upsert price: derivar `tier` via **join `store_id → stores.tier`** (hoje `collector.py:175` grava `store.get("tier",3)` do dict → linhas antigas dessincronizadas).
- Backfill one-off: `UPDATE prices p SET tier=s.tier FROM stores s WHERE s.id=p.store_id AND p.tier IS DISTINCT FROM s.tier`.

---

## FASE 4 — "Ignorar o erro" explícito (não-silencioso)
- `extracted>0, matched=0` (Doce Festa/Dona Dani/flyers de supermercado geral) → **INFO**, não warning; `_check_zero_products_alert` só p/ `extracted==0`.
- Roldão (flyer estático 2 itens, ETag/cache-hit) → `record_success` + INFO (já correto; validar ausência de alerta).

---

## FASE 5 — Validação local completa (ANTES de CI prod)
`ruff check . && mypy . && pytest tests/unit tests/schema -q` (1564+ green, 0 warn) · smoke motor embeddings (0 warning, dim/determinismo) · smoke tier 3 · health log limpo pós `pytest tests/unit` (0 linhas Dead/Fake/General) · `check_environment_parity` verde · cobertura 27/27 · `cleanup_price_fps --dry-run` = 0 resíduo.

---

## FASE 6 — CI PROD (gate final)
1. Branch única **`fix/zero-warn-scrapers`** (regra #13), commits por domínio: `deps+embeddings` → `tier3-health` → `tests-hermetic` → `prices-tier` → `warn-explicit`.
2. Push **WSL** → **CI watch até status FINAL** (verde ou RPR). Foco em: `ci.yml`, `scrape.yml`(dry)/smoke.
3. PR → squash merge → master green.
4. `Teste_Full_Manual` (dispatch) → SUCCESS.
5. `On Demand Scrape (force)` → SUCCESS. **Prova final:** snapshot limpo; health log com Kimbino/Portafolhetos; tiers 1/2a/3/4 coletando; `prices.tier` consistente; 0 warns.

---

## Ordem de dependência
```
0A (benchmark/pt → aprovação tabela) → 0B (runner real) → 0C (migração+deps)
→ 1 (tier3) → 2 (test pollution → merge sanitize-sweep) → 3 (prices.tier) → 4 (warns)
→ 5 (validação local 100%) → 6 (CI prod completo)
```

## Riscos e mitigação
- **e5-large/bge-m3 lentos no ubuntu 2-core** → 0B mede; gate de decisão no limite da máquina; fallback = `mpnet-multilingual`.
- **fastembed pode não ter FP32 do modelo** → `add_custom_model` com ONNX FP32 do HF; 0A decide FP32-vs-int8.
- **bge-m3 não no registro fastembed Python 0.8.0** → registrar via `add_custom_model` OU descartar; prioridade p/ `multilingual-e5-large` (nativo, 560M, FP32 via `qdrant/...`).
- **Mudança de modelo altera scores semânticos** → benchmark mede estabilidade do gate; wipe cache 1x evita vetores mistos; calibração re-validada.

---

## Confirmações fechadas
1. Ground truth do benchmark usa `prices`/`review_queue` reais (amostrados, não criados).
2. `embedding-benchmark.yml` = workflow permanente (dispatch manual, reusável p/ futuros upgrades).
3. `multilingual-e5-large` como candidato principal; `bge-m3` só se 0A mostrar ganho expressivo.