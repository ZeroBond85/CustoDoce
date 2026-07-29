"""
LLM Classifier - Orquestrador com Cache, Strategy Pattern e Graceful Degradation.

Pipeline (RFC Recurso 2 + 3 + Session Exhaustion):
    1. Verifica cache SQLite local (get_cache)
    2. Cache miss → itera providers [Groq → OpenRouter] (apenas 2 confiáveis)
    3. Cada provider tem Circuit Breaker (3 falhas → cooldown 60-300s backoff)
    4. 429 ABRE circuit do provider (evita martelar free-tier esgotado)
    5. Se TODOS providers configurados falharem → flag "LLM esgotado" por sessão
    6. Flag evita chamadas LLM pro resto do scrape → review_queue direto
    7. Caso todos falhem → fallback seguro {match: False, provider: fallback}

Compatibilidade:
    - Mantém API antiga `classify_sync(product_text, candidates)` que retorna
      dict com chaves {ingredient, confidence, reason}.
    - Internamente normaliza o resultado do Provider/LLM para esta shape.
"""

import contextlib

from parsers.llm_cache import get_cache, set_cache
from parsers.llm_strategies import (
    GroqStrategy,
    LLMResult,
    OpenRouterStrategy,
    _is_llm_exhausted,
    _set_llm_exhausted,
    reset_llm_exhausted,
)
from services.logger import logger


def _legacy_shape(result: LLMResult) -> dict:
    """Bridge entre o novo schema e o antigo usado por matcher pipeline."""
    return {
        "ingredient": result.canonical_name if result.match else None,
        "confidence": float(result.confidence_score) if result.match else 0.0,
        "reason": result.reason,
        "match": result.match,
        "provider": result.provider,
    }


def _fallback_result(reason: str = "Fallback: All LLM providers unavailable") -> dict:
    """Retorno seguro quando todos os providers falham."""
    return {
        "ingredient": None,
        "confidence": 0.0,
        "reason": reason,
        "match": False,
        "provider": "fallback",
    }


class LLMClassifier:
    """Orquestrador de classification LLM com session-level exhaustion."""

    def __init__(
        self,
        strategies: list | None = None,
    ):
        # Apenas 2 providers confiáveis no free-tier (Groq + OpenRouter)
        # Menos providers = menos latência, menos 429, fallback mais rápido
        self.strategies = strategies or [
            GroqStrategy(),
            OpenRouterStrategy(),
        ]

    def classify_sync(self, product_text: str, candidates: list) -> dict | None:
        """
        Compat entry-point — retorna None se ai/llm_classifier está desativado
        ou se nenhum provider tiver credencial configurada. Caso contrário
        retorna sempre um dict (nunca crash).
        """
        from services.config import get_feature as get_config

        if not get_config("features.ai.llm_classifier", ingredient=ingredient_name if (ingredient_name := (candidates[0].get("canonical_name") if candidates else None)) else None, default=False):
            return None

        if not candidates:
            return _fallback_result("No candidates provided")

        # If all configured providers are missing credentials, signal unavailability.
        has_config_check = [s for s in self.strategies if hasattr(s, "is_configured")]
        if has_config_check and not any(s.is_configured() for s in has_config_check):
            return None

        # 0. Reset session flags at start of scrape
        reset_llm_exhausted()

        # 1. Cache check
        cached = get_cache(product_text)
        if cached is not None:
            return cached

        # 2. Strategy iteration — early exit if session exhausted
        for strategy in self.strategies:
            if _is_llm_exhausted():
                logger.debug("LLM exhausted flag set, skipping remaining providers")
                break

            if hasattr(strategy, "is_configured") and not strategy.is_configured():
                continue
            try:
                result = strategy.classify(product_text, candidates)
                if result is not None:
                    shape = _legacy_shape(result)
                    # 3. Cache successful response
                    with contextlib.suppress(Exception):
                        set_cache(product_text, "", shape)
                    return shape
            except Exception as e:
                logger.warning(
                    "llm_strategy_unexpected_error",
                    provider=strategy.provider_name,
                    error=str(e),
                )
                continue

        # 4. All providers failed → set exhausted flag for rest of scrape
        _set_llm_exhausted(True)
        logger.info("All LLM providers failed, LLM exhausted for this scrape session")

        # 5. Graceful degradation
        return _fallback_result()

    def flush_cache(self):
        """Helper for cleanup routines."""
        from parsers.llm_cache import cleanup_ttl

        return cleanup_ttl()

    def reset_circuits(self):
        """Reseta circuit breakers + session exhausted flag (novo scrape)."""
        for s in self.strategies:
            if hasattr(s, "failure_count"):
                s.failure_count = 0
            if hasattr(s, "_consecutive_openings"):
                s._consecutive_openings = 0
            if hasattr(s, "_cooldown_seconds"):
                from parsers.llm_strategies import _get_cooldown_seconds

                s._cooldown_seconds = _get_cooldown_seconds()
        reset_llm_exhausted()


# ====================================================================
# Backwards compatibility — singleton-style API for legacy callers
# ====================================================================
_default_classifier = LLMClassifier()


def classify(product_text: str, candidates: list) -> dict | None:
    """Module-level convenience wrapper, mirrors old API."""
    return _default_classifier.classify_sync(product_text, candidates)


def reset_circuits() -> None:
    """Reseta os circuit breakers + exhausted flag do classifier singleton (novo scrape)."""
    _default_classifier.reset_circuits()
