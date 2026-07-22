# Design: Store Discovery + Dedup + Address + OCR Tier 3

> **Contexto:** Tier 3 (Tiendeo, Kimbino, Portafolhetos) já coleta flyers com `store_name` e `image_url`. Mas: (1) lojas novas não são descobertas, (2) lojas com nome variante duplicam, (3) endereço das lojas não é capturado, (4) OCR dos flyers não extrai produtos → preços.

## Arquitetura Atual

```
Agregador (scraper) → lista de flyers {store_name, image_url, ...}
    ↓ upsert_flyer() → flyers table (ocr_status='pending')
    ↓ process_ocr_queue() → flyer_ocr.py → products
    ↓ process_price_match() → upsert_price_rpc() ou review_queue
    ↓ discover_stores_from_flyers() RPC → store_registry (pending_review)
```

**O que já funciona:**
- `flyers` table com `store_name`, `image_url`, `region`, `ocr_status`
- `flyer_service.upsert_flyer()` — salva cada flyer
- `process_ocr_queue()` — pega flyers pendentes, roda OCR, extrai produtos, match/upsert
- `store_registry` table + `discover_stores_from_flyers()` RPC — descobre lojas novas
- `collect_aggregators_ssr()` e `collect_aggregators_js()` — chamam os scrapers Tier 3
- `_resolve_flyer_image()` — baixa página do catálogo pra extrair `image_url` real

**O que NÃO funciona / está incompleto:**
- `discover_stores_from_flyers()` RPC existe mas endereço não é extraído
- OCR só roda se o flyer tem `image_url` resolvida — muitos flyers de agregadores ficam sem imagem
- `store_name` vindo do scraper tem variações (ex.: "Assaí Atacadista" vs "Assai" vs "Assaí Atacadista - Santos")
- Nenhum endereço é capturado dos flyers ou PDFs
- Dedup de lojas por similaridade de nome existe (RapidFuzz >= 92%) mas endereço poderia reforçar

## Fluxo Proposto

```
┌─────────────────────────────────────────────────────────┐
│                   1. AGREGADOR                          │
│  TiendeoScraper / PlaywrightAggregatorScraper           │
│    ↓ coleta flyers com store_name + image_url + region   │
│    ↓ upsert_flyer() → flyers table                      │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│               2. STORE DISCOVERY                        │
│  discover_stores_from_flyers():                         │
│    2a. Lê store_name DISTINCT de flyers recentes        │
│    2b. Normaliza nome (upper + alnum)                   │
│    2c. Verifica se já existe em stores (por nome)       │
│    2d. Verifica se já existe em store_registry (pendente)│
│    2e. Se novo: insere store_registry (status=pendente) │
│    2f. Se similar (>=92%): preenche matched_store_id    │
│    2g. Extrai ADDRESS se disponível no flyer/PDF        │
│        (OCR da imagem do flyer ou campo no HTML)        │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│            3. OCR PIPELINE (process_ocr_queue)           │
│    3a. Pega flyers pendentes (ocr_status='pending')     │
│    3b. _resolve_flyer_image() → baixa image_url real   │
│    3c. Se imagem disponível:                            │
│        └─ extract_flyer_products() → lista de produtos  │
│             ├─ RapidOCR (dense) ou Vision-LLM (sparse)  │
│             ├─ match_ingredient() → match/score         │
│             ├─ process_price_match() → upsert ou review │
│             └─ ADDRESS EXTRACTION (novo):               │
│                  extrai endereço do texto OCR           │
│                  ex.: "R. XV de Novembro, 123 - Centro" │
│    3d. Se sem imagem: marca como failed                │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│           4. PRICE / STORE DEDUP                        │
│    Prices: ON CONFLICT (ingredient_id, store_id,         │
│             collected_at) DO UPDATE (já existe)          │
│    Stores: RapidFuzz >= 92% no nome normalizado          │
│    Address: Se store nova tem address + já existe store  │
│             com mesmo nome mas sem address → UPDATE      │
│    Review Queue: match < 55% vai pra revisão manual      │
└─────────────────────────────────────────────────────────┘
```

## Endereço: Onde e Como Capturar

### Fontes de Endereço por Tier

| Tier | Fonte | Como extrair | Prioridade |
|------|-------|-------------|------------|
| **1** (PDF) | PDF do flyer | OCR do texto do PDF + regex de endereço (`R\.\s+\w+.*\d+`) | Alta |
| **1** (API flyer) | JSON da API | Campo `address` no response da API | Alta |
| **2a** (VTEX) | `stores.yaml` + site | Já temos endereço manual no YAML; complementar via VTEX API de loja | Média |
| **2b** (Físico) | Manual | Já temos no YAML | Alta |
| **3** (Agregador) | Imagem do flyer + OCR | Extrair do texto OCR do flyer usando regex | Média |
| **3** (Agregador) | HTML do catálogo | Se o catalog page tiver endereço da loja, extrair com selectolax | Média |
| **4** (Manual) | Manual | Já temos | Alta |

### Como Armazenar

**Opção A — Expandir `stores` table:**
```sql
ALTER TABLE stores ADD COLUMN address TEXT DEFAULT '';
ALTER TABLE stores ADD COLUMN neighborhood TEXT DEFAULT '';
ALTER TABLE stores ADD COLUMN city TEXT DEFAULT '';
ALTER TABLE stores ADD COLUMN state TEXT DEFAULT 'SP';
ALTER TABLE stores ADD COLUMN zipcode TEXT DEFAULT '';
ALTER TABLE stores ADD COLUMN phone TEXT DEFAULT '';
ALTER TABLE stores ADD COLUMN latitude DECIMAL(10,7);
ALTER TABLE stores ADD COLUMN longitude DECIMAL(10,7);
ALTER TABLE stores ADD COLUMN address_source TEXT DEFAULT '';  -- 'ocr' | 'yaml' | 'api' | 'manual'
```

**Opção B — Tabela separada `store_units`:**
```sql
CREATE TABLE store_units (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id TEXT NOT NULL REFERENCES stores(id),
    name TEXT NOT NULL DEFAULT '',
    address TEXT DEFAULT '',
    neighborhood TEXT DEFAULT '',
    city TEXT DEFAULT '',
    state TEXT DEFAULT 'SP',
    zipcode TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    latitude DECIMAL(10,7),
    longitude DECIMAL(10,7),
    is_active BOOLEAN DEFAULT TRUE,
    source TEXT DEFAULT 'auto',          -- 'yaml' | 'api' | 'ocr' | 'manual'
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (store_id, address)
);
```

**Recomendação: Opção B.** Stores.yaml já tem `units: [{name, address}]` — essa estrutura se alinha com tabela separada. Uma loja (ex.: Assaí) pode ter múltiplas unidades em cidades diferentes.

### Regex de Endereço (para OCR)

```python
# Padrões de endereço em português
ADDRESS_PATTERNS = [
    r"(?:R\.|Rua|Av\.|Avenida|Alameda|Travessa|Praça|Estrada|Rodovia)\s+[^,]+,\s*\d+",
    r"(?:R\.|Rua|Av\.|Avenida|Alameda)\s+[^,\n]+",
    r"(?:CEP|Cep)\s*:?\s*\d{5}-?\d{3}",
    r"(?:Fone|Tel|Telefone|WhatsApp)\s*:?\s*\(?\d{2}\)?\s*\d{4,5}-?\d{4}",
    r"(?:Bairro|Centro|Jardim|Vila|Vila\s+\w+|Parque)\s+[^,\n]+",
]
```

## Score de Confiança para Endereço

| Situação | Pontos | Decisão |
|----------|--------|---------|
| Regex de rua + número | 10/10 | Salva automaticamente |
| Só bairro | 5/10 | Salva como parcial, marca `needs_review` |
| Só CEP | 7/10 | Salva mas sem endereço completo |
| Extraído de YAML/API | 10/10 | Confiável, sem revisão |
| Extraído de OCR com ruído | 4-7/10 | Salva + marca `address_confidence` |

## Dedup de Lojas — Estratégia Reforçada

### Pipeline de Dedup

```
store_name raw (ex.: "Assaí Atacadista - Santos")
    ↓ normalize_name(): upper + alnum + remove " - " e sufixos de cidade
    → "ASSAI ATACADISTA"
    ↓ find_similar_stores(): RapidFuzz token_set_ratio >= 92%
    ├── Se match: store já existe → linked_store_id = match.id
    │   └── Se address disponível e store existente não tem → UPDATE address
    └── Se NO match: nova store → insert em store_registry
         └── Se address disponível → salva junto no registry
```

### Novos Campos em `store_registry`

```sql
ALTER TABLE store_registry 
    ADD COLUMN address TEXT DEFAULT '',
    ADD COLUMN neighborhood TEXT DEFAULT '',
    ADD COLUMN phone TEXT DEFAULT '',
    ADD COLUMN address_confidence DECIMAL(3,2) DEFAULT 0,
    ADD COLUMN discovery_source TEXT DEFAULT 'flyer',  -- 'flyer' | 'yaml' | 'api'
    ADD COLUMN region TEXT DEFAULT '';
```

## OCR Pipeline — Melhorias

### 1. Resolução de Imagem (já existe, melhorar)

`_resolve_flyer_image()` atualmente baixa a página do catálogo pra achar a imagem real do flyer.
Melhoria: se a imagem já veio no scraper (Tiendeo já retorna `image_url`), pular resolução.

### 2. Extração de Produto (já existe)

`extract_flyer_products()` → RapidOCR / Vision-LLM → match → upsert.

### 3. Extração de Endereço (NOVO)

Após OCR, no mesmo texto extraído, aplicar regex de endereço.
Se achar endereço com confiança >= 7/10:
  - Atualizar `flyer.address` 
  - Se store já existe em `stores` sem address → UPDATE
  - Se store é nova → salvar no `store_registry.address`

### 4. Store Discovery Automática

`discover_stores_from_flyers()` RPC já existe. Vamos expandi-la pra:
- Extrair `region` de cada flyer e salvar como `store_registry.region`
- Extrair `address` do texto OCR e salvar como `store_registry.address`
- Atualizar `match_score` baseado em similaridade com stores existentes

## Tabelas Novas / Alteradas

### `store_units` (NOVA)
```sql
CREATE TABLE store_units (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    unit_name TEXT DEFAULT '',
    address TEXT DEFAULT '',
    neighborhood TEXT DEFAULT '',
    city TEXT DEFAULT '',
    state TEXT DEFAULT 'SP',
    zipcode TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    latitude DECIMAL(10,7),
    longitude DECIMAL(10,7),
    source TEXT DEFAULT 'auto',        -- 'yaml' | 'api' | 'ocr' | 'manual'
    confidence DECIMAL(3,2) DEFAULT 1.0,
    is_active BOOLEAN DEFAULT TRUE,
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (store_id, address)
);
```

### `store_registry` — novos campos
```sql
ALTER TABLE store_registry ADD COLUMN address TEXT DEFAULT '';
ALTER TABLE store_registry ADD COLUMN neighborhood TEXT DEFAULT '';
ALTER TABLE store_registry ADD COLUMN phone TEXT DEFAULT '';
ALTER TABLE store_registry ADD COLUMN address_confidence DECIMAL(3,2) DEFAULT 0;
ALTER TABLE store_registry ADD COLUMN discovery_source TEXT DEFAULT 'flyer';
ALTER TABLE store_registry ADD COLUMN region TEXT DEFAULT '';
```

### `flyers` — campo address
```sql
ALTER TABLE flyers ADD COLUMN address TEXT DEFAULT '';
ALTER TABLE flyers ADD COLUMN address_confidence DECIMAL(3,2) DEFAULT 0;
```

## Implementação — Ordens

### Fase 1: Address no OCR (backend Python)
- [ ] Adicionar `extract_address_from_text()` em `parsers/address_extractor.py` (regex + score)
- [ ] Integrar no `process_ocr_queue()`: após OCR, extrair address do texto
- [ ] Salvar address no flyer + store_registry

### Fase 2: Store Discovery Reforçada
- [ ] Expandir `discover_stores_from_flyers()` pra incluir address + region
- [ ] Atualizar `store_registry.upsert_registry_entry()` com novos campos
- [ ] Adicionar merge de address: se store existente sem address + registry tem → UPDATE

### Fase 3: Store Units Table
- [ ] Migration SQL: criar `store_units` table
- [ ] Sincronizar `stores.yaml` units → `store_units` table (em `sync_store_fields()`)
- [ ] Populate `store_units` from store_registry quando aprovada

### Fase 4: Dashboard — Revisão de Lojas
- [ ] Página no dashboard: "Lojas Descobertas" (store_registry pendentes)
- [ ] Botão "Aprovar + Mapear Endereço" 
- [ ] Botão "Rejeitar"

### Fase 5: OCR Tier 3 (já existe, validar)
- [ ] Verificar se `collect_aggregators_ssr()` + `collect_aggregators_js()` estão no `load_stores()` 
- [ ] Verificar se `process_ocr_queue()` está na `TIER_PLAN` (sim, linha 93)
- [ ] Testar OCR real com flyers do Tiendeo

## Pendências Críticas Identificadas no Audit

### P0.1 — Non-food filter DEVE rodar ANTES do store_registry

**Problema:** `discover_stores_from_flyers()` RPC lê TODOS os `store_name` distintos da tabela `flyers` e insere em `store_registry`. Isso inclui lojas não-alimentícias como Boticário, Magazine Luiza, Drogasil. O `cleanup_non_food_flyers()` roda DEPOIS, mas as entries no registry já foram criadas.

**Correção:** Modificar a chamada Python `discover_stores_from_flyers()` em `store_registry.py` para pular nomes que contêm `NON_FOOD_KEYWORDS` (já definido em `flyer_service.py:159`). Ou modificar o RPC no PostgreSQL para aceitar um filtro.

**Decisão:** Fazer no Python — `store_registry.discover_stores_from_flyers()` filtra antes de chamar o RPC.

### P0.2 — Alias mapping para nomes de loja entre agregadores

**Problema:** O mesmo supermercado aparece com nomes diferentes em cada agregador:
- Tiendeo: `"Assaí Atacadista"` (do `data-testid="flyer_item_retailer_name"`)
- Kimbino: `"Assai"` (do CSS pattern `class="shop..."`)
- Normalizados: `"ASSAI ATACADISTA"` vs `"ASSAI"` → RapidFuzz `token_set_ratio` = 100% ✓ (funciona porque um é subconjunto do outro)

Mas nomes como `"Supermercados Guanabara"` vs `"Guanabara"` podem variar. O `token_set_ratio` (que compara conjuntos de tokens) é resiliente pra esse caso. O threshold de 92% está OK, mas podemos adicionar um **fallback de 80%** especificamente para o discovery, onde o custo de falso positivo é baixo (vai pra review).

**Decisão:** Manter 92% para dedup automático. Adicionar 80% como fallback no discovery — se similar >= 80%, incluir `matched_store_id` + `match_score` + marcar como `pending_review` (não auto-merge).

### P0.3 — OCR de Tier 3 NUNCA foi testado com flyer real

**Problema:** O pipeline `process_ocr_queue()` → `extract_flyer_products()` funciona para PDFs baixados localmente, mas flyers de agregadores dependem de:
1. `_resolve_flyer_image()` — baixar a página do catálogo pra achar a URL real da imagem
2. Muitos flyers do Tiendeo já têm `image_url` direta no scraper (campo `img_big`)
3. Kimbino/Portafolhetos retornam `img_src` direto

**Risco real:** Se `_resolve_flyer_image()` falhar ou se a imagem do agregador for protegida (hotlink protection), o OCR nunca roda. **Isso precisa ser verificado na prática antes de considerar o pipeline funcional.**

**Teste:** Baixar 1 flyer real do Tiendeo e rodar `extract_flyer_products()` manualmente.

### P0.4 — `image_hash` não é consistente entre agregadores

**Problema:** Tiendeo gera hash como `"catalog_123"`, Kimbino como `hash(img_src_or_url)`. O mesmo flyer (ex.: Carrefour da semana) aparece no Tiendeo e no Kimbino com hashes diferentes. Isso é ACEITÁVEL porque:
- A UNIQUE `(store_name, region, image_hash)` é por agregador (cada um tem seu `source`)
- O dedup real acontece na tabela `prices` com `(ingredient_id, store_id, collected_at)`
- Processar o mesmo flyer 2x é redundante mas não quebra nada

**Decisão:** Não alterar. Aceitar redundância de OCR entre agregadores — o dedup de preços no SQL resolve.

## Riscos Atualizados

| Risco | Probabilidade | Impacto | Mitigação |
|-------|-------------|---------|-----------|
| OCR de flyer de agregador não acha produtos | Alta | Produto sem preço | Vision-LLM fallback + melhorar resolução de imagem |
| Endereço extraído do OCR é ruidoso | Média | Address errado | Score de confiança + revisão manual |
| Store discovery cria muitas falsas lojas | Média | Poluição no DB | Dedup >= 92% + review obrigatório |
| Store name do scraper é genérico ("Supermercado") | Média | Match falso | Ignorar nomes genéricos (lista de exclusão) |
| Flyer sem image_url (não resolve) | Alta | OCR não roda | Priorizar scraper que já retorna image_url |
| **Non-food stores poluem store_registry** | **Alta** | **Lixo no DB** | **Filtrar antes de inserir (P0.1)** |
| **Mesma loja com nomes diferentes entre agregadores** | **Média** | **Store duplicada no registry** | **Fallback 80% + matched_store_id (P0.2)** |
| **OCR de flyer de agregador nunca testado** | **Alta** | **Pipeline inteiro pode falhar** | **Teste real na Fase 4 (P0.3)** |
