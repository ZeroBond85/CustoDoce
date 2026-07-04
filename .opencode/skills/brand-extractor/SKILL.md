---
name: brand-extractor
description: Extrai brand de produto: 3 níveis (word-boundary exact > substring boundaries > fuzzy RapidFuzz ≥80%). Funções reais: extract_brand() → str, extract_brand_from_all() → str | None.
---
# brand-extractor

3-level brand extraction strategy implementada em `parsers/brand_extractor.py`.

## API Real

```python
from parsers.brand_extractor import extract_brand, extract_brand_from_all
from services.types import Ingredient

# Single ingredient brand extraction
def extract_brand(product_text: str, ingredient: Ingredient) -> str: ...

# Multi-ingredient brand extraction (de-duplicated)
def extract_brand_from_all(
    product_text: str,
    ingredients: list[Ingredient],
    threshold: float = 85.0,
) -> str | None: ...
```

`extract_brand()` retorna o nome da marca (string) ou `"Desconhecido"`.
`extract_brand_from_all()` retorna a marca ou `None`.

## 3 Níveis (em ordem)

| Nível | Método | Retorna |
|-------|--------|---------|
| 1 | Word-boundary regex `\bbrand\b` | Marca se match exato |
| 2 | Substring com boundary `(?<![A-Z])brand(?![A-Z])` | Marca se match não-embarcado |
| 3 | RapidFuzz `fuzz.ratio()` por palavra ≥80% | Marca se score ≥80, senão "Desconhecido" |

Todos os níveis normalizam acentos via unicodedata (NFD) antes de comparar.

## Exemplos (testes reais)

```python
assert extract_brand("Leite Condensado Moça 395g", ing) == "Moça"
assert extract_brand("Leite Piracanjuba 1kg", ing) == "Piracanjuba"
assert extract_brand("Leite Condensado Genérico", ing) == "Desconhecido"
assert extract_brand("LEITE CONDENSADO MOÇA 395G", ing) == "Moça"

assert extract_brand_from_all("Chocolate Melken 1kg", ings) == "Melken"
assert extract_brand_from_all("Produto Genérico", ings) is None
```

## Antipatterns

- ❌ Retornar dict `{brand, level, confidence}` (API real retorna string)
- ❌ Usar case-sensitive (código normaliza uppercase)
- ❌ Hardcoded brand list (vem de `config/ingredients.yaml`)
- ❌ Ignorar acentuação (código normaliza NFD)

## Uso no Pipeline

```python
from parsers.brand_extractor import extract_brand

brand = brand or extract_brand(raw_product, ingredient)
# brand → "Moça" | "Nestlé" | "Desconhecido"
```
