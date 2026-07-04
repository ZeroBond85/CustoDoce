---
name: price-normalizer
description: "Normaliza raw_price + raw_unit → qty, unit_kg, total_kg, price_per_kg, price_per_un via NormalizedPrice class"
---
# price-normalizer

Normaliza preços brutos de scrapers para formato padronizado. Implementação em `parsers/normalizer.py`.

## API Real

```python
from parsers.normalizer import normalize_price, parse_unit, NormalizedPrice

# Parsing de unidade + cálculo de preço
result = normalize_price(47.90, "cx 12x395g")
# result → NormalizedPrice(qty=12, unit_kg=0.395, total_kg=4.74, price_per_kg=10.11, price_per_un=3.99)

# Apenas parsing de unidade (sem preço)
parsed = parse_unit("cx 12x395g")
# parsed → NormalizedPrice(qty=12, unit_kg=0.395, total_kg=4.74, price_per_kg=0.0, price_per_un=0.0)

# Converter para dict
parsed.to_dict()
# → {"qty": 12, "unit_kg": 0.395, "total_kg": 4.74, "price_per_kg": 10.11, "price_per_un": 3.99}
```

Ambas retornam `NormalizedPrice | None` (None se input inválido).

## Parsing Rules

| Padrão | Exemplo | qty | unit_kg | total_kg |
|---------|---------|-----|---------|----------|
| `N x N kg/g` | `cx 12x395g` | 12 | 0.395 | 4.74 |
| `N x N kg/g` | `12x395g` | 12 | 0.395 | 4.74 |
| `N kg` | `2kg` | 1 | 2.0 | 2.0 |
| `N g/ml` | `500g` | 1 | 0.5 | 0.5 |
| `N un` + weight | `12un 395g` | 12 | 0.395 | 4.74 |
| `pacote com N` | `pacote com 12` | 12 | 0.0 | 0.0 (fallback) |

## Parsing Logic (Real)

```python
# Vírgula BR é convertida para ponto
raw_unit = raw_unit.strip().replace(",", ".")  # "0,395" → "0.395"

# 4 regex patterns em ordem: cx N x N kg/g, N kg/g, N x N (sem unidade)
# + 4 patterns para unidade: un, pacote com, cx com, cx
parse_unit()
```

## CRITICAL: Bool Protection (regra #7 do AGENTS.md)

`normalized` pode ser `true` (bool) ou `None`. SEMPRE proteger:

```python
if isinstance(normalized, NormalizedPrice):
    total_kg = normalized.total_kg
else:
    total_kg = 1.0
```

## Fórmula

```python
price_per_kg = round(raw_price / total_kg, 2)
price_per_un = round(raw_price / qty, 2)
```

## Edge Cases

| Input | Handling |
|-------|----------|
| `cx12x395g` (sem espaço) | Regex com `\s*` aceita ambos |
| `395g` (sem qty) | qty = 1 |
| None/null | `parse_unit()` retorna None |
| `normalized = True` | `isinstance` guard protege |

## Test Cases

```python
p = normalize_price(47.90, "cx 12x395g")
assert p is not None
d = p.to_dict()
assert d["qty"] == 12
assert d["unit_kg"] == 0.395

p2 = normalize_price(10.0, "2kg")
assert p2 is not None
assert p2.to_dict()["total_kg"] == 2.0

assert normalize_price(0, "1kg") is None  # preço zero
```

## Antipatterns

- ❌ `normalized.get()` sem `isinstance(normalized, NormalizedPrice)`
- ❌ Hardcoded kg conversion factors
- ❌ Não tratar decimal com vírgula (BR format: `0,395`)
- ❌ Ignorar None return (sempre verificar antes de usar)
