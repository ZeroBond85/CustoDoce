# Troubleshooting
> Última atualização: 2026-07-15 03:22 UTC

Guia de problemas comuns e soluções.

## Scraper Issues

### PDF não é processado (pdfplumber retorna vazio)

**Sintoma:** Flyer baixado mas nenhum preço extraído.

**Diagnóstico:**
```bash
python -c "
from scrapers.flyer_scraper import FlyerScraper
from scrapers.ocr import ocr_pdf
from pathlib import Path

pdf_path = Path('data/test_flyer.pdf')
text = ocr_pdf(pdf_path.read_bytes())
print(text[:500])
"
```

**Soluções:**
1. Verificar se é PDF válido (não imagem digitalizada):
   ```bash
   file flyer.pdf  # deve mostrar "PDF document"
   ```
2. Habilitar OCR fallback: o scraper já faz isso automaticamente (`flyer_scraper.py` linha ~140)
3. Verificar se o PDF tem texto selecionável ou é imagem escaneada
4. Se for escaneado: verificar se Tesseract está instalado com OCR português
   ```bash
   tesseract --version  # deve mostrar 5.x
   tesseract --list-langs  # deve incluir "por"
   ```

---

### Matcher coloca muito na review queue (confidence <80%)

**Sintoma:** Centenas de itens em `review_queue` após scrape.

**Diagnóstico:**
```python
from services.dashboard_queries import get_review_queue_cached
queue = get_review_queue_cached(limit=10)
for item in queue:
    print(f"{item['product_name']} → {item['match_reason']} (conf={item['match_confidence']:.2f})")
```

**Soluções:**
1. **Nome do ingrediente muito diferente do produto**: adicionar alias em `config/ingredients.yaml`
   ```yaml
   - canonical: "Leite Condensado"
     aliases:
       - "Leite Cond. Moça"    # ← novo alias
   ```
2. **Marca poluindo o matcher**: ajustar `brand_priority` em `parsers/brand_extractor.py`
3. **Unidade mal parseada**: verificar `parsers/unit_extractor.py` para padrões como "cx 12x395g"
4. **Fuzzy ratio no limite**: o matcher já usa blend RapidFuzz + embeddings para 65-80%

**Prevenção:** Rodar `scripts/sanity_check.py` antes de cada coleta grande.

---

### Scraper dá timeout em site VTEX

**Sintoma:** `requests.Timeout` em `vtex_scraper.py`.

**Diagnóstico:**
```bash
python -c "
from scrapers.vtex_scraper import VtexScraper
s = VtexScraper({'name':'Tenda','base_url':'https://www.tendaatacado.com.br'})
print(s.check_health())  # 200 ou erro
"
```

**Soluções:**
1. Verificar se a loja mudou de plataforma (algumas migraram de VTEX)
2. Checar rate limit: VTEX API permite 200 req/min para search
3. Adicionar retry com backoff exponencial:
   ```python
   for attempt in range(3):
       try:
           return fetch_with_timeout(url)
       except TimeoutError:
           time.sleep(2 ** attempt)  # 1s, 2s, 4s
   ```

---

### Playwright não encontra elementos (CSS selector quebrado)

**Sintoma:** `Selector not found` em `playwright_price_scraper.py`.

**Diagnóstico:**
```python
from scrapers.playwright_price_scraper import PlaywrightPriceScraper
s = PlaywrightPriceScraper({'name':'Tiendeo','selectors': {'product_name':'.product-name'}})
with s._get_page('https://example.com') as page:
    content = page.content()
    print('product-name found:', '.product-name' in content)
```

**Soluções:**
1. O site mudou o CSS. Atualizar selectors em `config/stores.yaml`
2. Usar `data-testid` ao invés de classes CSS (mais estável)
3. Executar `scripts/discover_urls.py --store NOME` para re-descobrir URLs

---

## Database Issues

### Supabase connection timeout

**Sintoma:** `Connection timeout` ou `Could not connect to server`.

**Diagnóstico:**
```bash
python -c "
import os
from supabase import create_client
client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
print(client.table('stores').select('name').limit(1).execute())
"
```

**Soluções:**
1. Verificar se IP está na whitelist do Supabase (Settings > Database > Connection Pooling)
2. Usar RPC (porta 443) ao invés de psycopg2 direto:
   ```python
   # ✅ RPC funciona de qualquer rede
   client.rpc('exec_sql_query', {'query': 'SELECT 1'}).execute()
   # ❌ psycopg2 pode falhar (porta 5432 bloqueada)
   ```
3. Verificar se o projeto Supabase está ativo (não pausado por inatividade)
4. Testar com `scripts/deploy_check.py --health`

---

### RPC `upsert_price_rpc` retorna erro de conflicting row

**Sintoma:** `duplicate key value violates unique constraint`.

**Solução:** O RPC já faz dedup por `store_id + ingredient_id + raw_unit + raw_price`. Se ainda dá conflito, verificar se há constraint customizada:
```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname LIKE '%price%';
```
Se existir constraint extra, ajustar o RPC em `supabase/functions/upsert_price_rpc/`.

---

### Schema validation falha no CI

**Sintoma:** `scripts/validate_db_schema.py` retorna 87+ errors no deploy.

**Diagnóstico:**
```bash
python scripts/validate_db_schema.py --verbose
```

**Soluções comuns:**
1. **Falta coluna**: rodar `supabase/consolidated_migration.sql` novamente
   ```bash
   python scripts/deploy_database.py --dry-run
   python scripts/deploy_database.py --execute
   ```
2. **Índice faltando**: criar manualmente (ver output do validate_db_schema.py)
3. **Função com signature diferente**: dropar e recriar
   ```sql
   DROP FUNCTION IF EXISTS upsert_price_rpc(jsonb);
   -- re-criar do migration file
   ```

---

## Dashboard Issues

### Streamlit Cloud: "Application error"

**Sintoma:** App não carrega no Streamlit Cloud.

**Diagnóstico:**
1. Checar logs em Streamlit Cloud > Deploys > Recent deploys
2. Verificar se todos os secrets estão configurados (Settings > Secrets)

**Soluções:**
1. `AttributeError` ou `ModuleNotFoundError`: verificar `requirements.txt` inclui todas as dependências
2. Timeout: Streamlit Cloud timeout é 30s para inicialização. Reduzir imports preguiçosos:
   ```python
   # imports lazy (no topo do arquivo)
   # from expensive_module import thing  # não fazer
   # Fazer: thing = lazy_import("expensive_module.thing")
   ```
3. Missing secrets: configurar `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` em Streamlit Cloud Secrets

---

### Dashboard mostra dados desatualizados

**Sintoma:** Preços antigos, gráfico não atualiza.

**Soluções:**
1. Limpar cache do Streamlit: sidebar > "Limpar Cache" (botão no sidebar)
2. Ou via código:
   ```python
   from services.dashboard_queries import clear_all_caches
   clear_all_caches()
   ```
3. Verificar se scrape está rodando: GitHub Actions > `scrape.yml` > latest run

---

### Página não encontrada (404) após deploy

**Sintoma:** `dashboard/pages/minha_pagina.py` existe mas não aparece.

**Soluções:**
1. Verificar se está em `admin/app.py`:
   ```python
   from dashboard.pages.minha_pagina import render_minha_pagina  # ← importado
   PAGE_FUNCTIONS = {
       ...
       "minha_pagina": render_minha_pagina,  # ← registrado
   }
   ```
2. Verificar se está em `dashboard/components/layout.py`:
   ```python
   PAGES = [
       ...
       ("minha_pagina", "🏷️", "Minha Página"),  # ← no menu
   ]
   ```

---

## Quality Gates

### Great Expectations falha: `price_per_kg > 0` não passa

**Sintoma:** `scripts/run_quality_gates.py` retorna exit code 1.

**Diagnóstico:**
```bash
python -c "
from services.price_repository import get_all_current_prices
prices = get_all_current_prices(valid_only=False, limit=1000)
bad = [p for p in prices if p.get('normalized',{}).get('price_per_kg',0) <= 0]
print(f'Bad prices: {len(bad)}')
for p in bad[:5]:
    print(p['product_name'], p.get('normalized'))
"
```

**Solução:** Dados de scraper com parsing de unidade quebrado. Verificar `parsers/normalizer.py` para o padrão de unidade problemático.

---

### Great Expectations falha: `match_confidence >= 0.55` não passa

**Sintoma:** Muita sujeira no DB com confidence baixa.

**Solução:** A regra de quality gate é `>=0.55` (não `>=0.80`). Itens entre 0.55 e 0.80 vão para review queue (comportamento esperado). Se há muitos com confidence < 0.55, significa que o matcher está funcionando mal — verificar logs de scrape.

---

## GitHub Actions / CI

### CI falha em PR de fork

**Sintoma:** Job `integration` não roda em PR externo.

**Solução:** Comportamento esperado. PRs de fork não têm acesso a secrets (proteção GitHub). Testar localmente:
```bash
export SUPABASE_URL=...
export SUPABASE_SERVICE_ROLE_KEY=...
python -m pytest tests/integration/ -q
```

---

### `real` job nunca termina

**Sintoma:** Timeout em `tests/real/`.

**Solução:** Scrapers reais são slow + flaky (marcados `@pytest.mark.real`). Não rodar em CI normal. Executar manualmente:
```bash
python -m pytest tests/real/test_vtex_scrapers.py -v -m real
```

---

## Email / Notifications

### Gmail SMTP: "Authentication failed"

**Sintoma:** Email não enviado, erro `SMTP Authentication failed`.

**Soluções:**
1. Verificar que "Less secure app access" está habilitado OU usar App Password
2. Se 2FA: usar App Password (não senha normal)
   ```
   Gmail > Security > 2-Step Verification > App Passwords
   ```
3. Verificar se `SMTP_USER` e `SMTP_PASSWORD` estão corretos nos secrets

---

## Como reportar problema novo

1. Rodar `scripts/sanity_check.py` e incluir output
2. Se scraper: incluir output de `scripts/store_health_check.py`
3. Se DB: incluir output de `scripts/validate_db_schema.py`
4. Abrir issue com: OS, Python version, steps to reproduce, expected vs actual
