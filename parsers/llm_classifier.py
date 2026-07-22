"""
LLM Classifier - Orquestrador com Cache, Strategy Pattern e Graceful Degradation.

Pipeline (RFC Recurso 2 + 3):
    1. Verifica cache SQLite local (get_cache)
    2. Cache miss → itera providers [Groq → OpenRouter → HuggingFace]
    3. Cada provider tem Circuit Breaker (3 falhas → 10 min cooldown)
    4. Caso todos falhem → fallback seguro {match: False, provider: fallback}

Compatibilidade:
    - Mantém API antiga `classify_sync(product_text, candidates)` que retorna
      dict com chaves {ingredient, confidence, reason}.
    - Internamente normaliza o resultado do Provider/LLM para esta shape.
"""

import contextlib

from parsers.llm_cache import get_cache, set_cache
from parsers.llm_strategies import (
    DeepSeekStrategy,
    GitHubModelsStrategy,
    GoogleStrategy,
    GroqStrategy,
    HuggingFaceStrategy,
    LLMResult,
    MistralStrategy,
    NVIDIAStrategy,
    OpenAIStrategy,
    OpenRouterStrategy,
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
    """Orquestrador de classification LLM."""

    def __init__(
        self,
        strategies: list | None = None,
    ):
        self.strategies = strategies or [
            GroqStrategy(),
            OpenRouterStrategy(),
            HuggingFaceStrategy(),
            GoogleStrategy(),
            OpenAIStrategy(),
            MistralStrategy(),
            DeepSeekStrategy(),
            NVIDIAStrategy(),
            GitHubModelsStrategy(),
        ]

    def classify_sync(self, product_text: str, candidates: list) -> dict | None:
        """
        Compat entry-point — retorna None se ai/llm_classifier está desativado
        ou se nenhum provider tiver credencial configurada. Caso contrário
        retorna sempre um dict (nunca crash).
        """
        from services.config import get as get_config

        if not get_config("features.ai.llm_classifier", True):
            return None

        if not candidates:
            return _fallback_result("No candidates provided")

        # If all configured providers are missing credentials, signal unavailability.
        # Strategies that don't implement is_configured() (e.g., test mocks) are
        # always considered "available".
        has_config_check = [s for s in self.strategies if hasattr(s, "is_configured")]
        if has_config_check and not any(s.is_configured() for s in has_config_check):
            return None

        # 1. Cache check
        cached = get_cache(product_text)
        if cached is not None:
            return cached

        # 2. Strategy iteration
        for strategy in self.strategies:
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

        # 4. Graceful degradation
        return _fallback_result()

    def flush_cache(self):
        """Helper for cleanup routines."""
        from parsers.llm_cache import cleanup_ttl

        return cleanup_ttl()

    def reset_circuits(self):
        """Reseta o estado dos circuit breakers de todos os providers.

        Usado no início de um novo scrape para que um provider que recuperou
        (ex.: Groq free-tier) seja tentado novamente do zero. Os strategies são
        instâncias efêmeras por padrão, mas o singleton _default_classifier as
        mantém; este método zera o contador/cooldown de cada um.
        """
        for s in self.strategies:
            if hasattr(s, "failure_count"):
                s.failure_count = 0
            if hasattr(s, "_consecutive_openings"):
                s._consecutive_openings = 0
            if hasattr(s, "_cooldown_seconds"):
                from parsers.llm_strategies import _get_cooldown_seconds

                s._cooldown_seconds = _get_cooldown_seconds()


# ====================================================================
# Backwards compatibility — singleton-style API for legacy callers
# ====================================================================
_default_classifier = LLMClassifier()


def classify(product_text: str, candidates: list) -> dict | None:
    """Module-level convenience wrapper, mirrors old API."""
    return _default_classifier.classify_sync(product_text, candidates)


def reset_circuits() -> None:
    """Reseta os circuit breakers do classifier singleton (novo scrape)."""
    _default_classifier.reset_circuits()
