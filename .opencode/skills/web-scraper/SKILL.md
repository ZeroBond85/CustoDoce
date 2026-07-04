---
name: web-scraper
description: "CustoDoce 3-tier scraping: PDF (9 atacadistas), VTEX API (e-commerce), agregadores (Tiendeo/Guiato). Self-healing via services/scraper_health.py"
---

# web-scraper

3-tier scraping strategy para CustoDoce.

## 3 Tiers de Coleta

| Tier | Tipo | Frequência | Método |
|------|------|------------|--------|
| 1 | PDF Direto (9 redes) | Semanal (qua/qui) | pdfplumber + OCR |
| 2a | E-commerce SP (VTEX) | Diária | requests API |
| 2b | Atacado Físico SP | Mensal | Planilha manual |
| 3 | Agregadores (Tiendeo/Guiato) | Fallback | Playwright/SSR |

## Tier 1: PDF Scraper

```python
# Fluxo
build_url() → HEAD (ETag cache) → download → MD5 cache
→ pdfplumber → OCR fallback (Tesseract)
→ extract_prices() → process_price_match()
```

### 9 Redes Ativadas
- Exemplo: Extra, Pão de Açúcar, Mercadao, etc.

### Self-Healing (obrigatório)

Use `services/scraper_health.py` — o ponto único de self-healing do projeto.

```python
from services.scraper_health import record_failure, record_success

def scrape_store(store_id: str):
    try:
        data = scrape(url)
        record_success(
            scraper_name=store_id,
            items_found=len(data),
            products_matched=matched,
        )
    except Exception as e:
        record_failure(
            scraper_name=store_id,
            reason=str(e),
            attempted_by="auto",
        )
```

## Tier 2a: VTEX API

```python
# Endpoint
GET api/products/search?ft=<ingredient>

# Parsing
response.json() → iterate products
```

### Stores VTEX (e-commerce SP)
- Identificadas em `config/stores.yaml` com `tier: 2a`

## Tier 3: Agregadores

```python
# Tiendeo / Guiato
GET /busca?q=<ingredient> → selectolax CSS selectors
```

Usa Playwright para sites com SSR (JavaScript rendering).

## Anti-Patterns

- ❌ Não usar `psycopg2` direto (porta 5432 bloqueada)
- ❌ Não salvar em arquivo local (usar Supabase RPC)
- ❌ Não ignorar ETag (cache hit é bom)
- ❌ Não fazer scraping sem `record_failure/success()`

## Configuração

```yaml
# config/stores.yaml
- store_name: "Extra"
  tier: 1
  frequency_minutes: 10080  # semanal
  scraper_type: pdf
  url_template: "https://exemplo.com/flyer/{date}"
```

## Output

```python
{
    "store_id": "uuid",
    "ingredient_id": "leite_condensado",
    "raw_product": "Leite Condensado Italac 395g",
    "raw_price": 12.99,
    "raw_unit": "12x395g",
    "source": "pdf",
    "tier": 1
}
```