---
name: llm-integration
description: "LLMClassifier com multi-provider (Groq → OpenRouter → HuggingFace), semantic matching (sentence-transformers), cache SQLite e circuit breaker"
---
# llm-integration

Classificação LLM para ingredient matching. Implementação em `parsers/llm_classifier.py`.

## Matching Cascade (real)

Fonte: `AGENTS.md` + `parsers/matcher.py` + `services/collector.py`

| Confidence | Método | Ação |
|-------------|--------|------|
| ≥80% | RapidFuzz exact | Auto-accept |
| 55-79% | RapidFuzz (0.6) + Embeddings (0.4) blend | Auto-accept |
| 65-80% | LLM Classifier (Groq → OpenRouter → HF) | Auto-accept |
| <55% | Todos falham | review_queue |

> Nota: LLM só é consultado para candidatos 65-80%. Fora dessa faixa, auto-accept (>80) ou review_queue (<55).

## LLMClassifier API

```python
from parsers.llm_classifier import LLMClassifier, classify

# Module-level convenience (singleton)
result = classify("Leite Condensado Moça 395g", candidates)
# result → {"ingredient": "leite_condensado", "confidence": 0.92, "reason": "...", "match": True, "provider": "groq"}

# Orquestrador completo
clf = LLMClassifier()
result = clf.classify_sync("Leite Condensado Moça 395g", candidates)
```

## Multi-Provider Pipeline

```
1. Cache check (SQLite local via parsers/llm_cache.py)
2. Strategy iteration:
   a. GroqStrategy (llama-3.3-70b-versatile) ← GROQ_API_KEY
   b. OpenRouterStrategy ← OPENROUTER_API_KEY
   c. HuggingFaceStrategy ← HUGGINGFACE_API_KEY
3. Cada strategy tem Circuit Breaker (3 falhas → 10 min cooldown)
4. Fallback: {match: False, provider: "fallback"}
```

## Semantic Matching

```python
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

model = SentenceTransformer('all-MiniLM-L6-v2')

embed1 = model.encode("Leite Condensado Moça 395g").tolist()
embed2 = model.encode("leite condensado").tolist()
score = cosine_similarity([embed1], [embed2])[0][0]
```

## Review Queue Entry

```python
{
    "raw_product": str,
    "ingredient_id": str | None,
    "store_id": str,
    "confidence": float,
    "match_reason": str,
    "match_type": "exact" | "fuzzy" | "semantic" | "llm" | "review",
    "top3": [{"id": str, "name": str, "score": float}],
    "status": "pending"
}
```

## Caching (SQLite local)

```python
# parsers/llm_cache.py
get_cache(product_text)       → dict | None
set_cache(product_text, query, result)
cleanup_ttl()                 # remove expirados (30 dias)
```

## Environment

```bash
GROQ_API_KEY=xxx              # primary
OPENROUTER_API_KEY=xxx        # fallback 1
HUGGINGFACE_API_KEY=xxx       # fallback 2
```

Features: `config/features.yaml → features.ai.llm_classifier`

## Fallback

Se todos providers falham → retorno `{match: False, provider: "fallback"}` com confidence 0.0.
