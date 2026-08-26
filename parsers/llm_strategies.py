"""
LLM Strategy Pattern com Circuit Breaker e JSON Mode.

Objetivo (RFC Recurso 2): Evitar crashes do pipeline quando APIs externas caem.
- Cada provider implementa o mesmo contrato (LLMStrategy ABC).
- Tenta Groq (primário) → OpenRouter (fallback 1) → para.
- JSON Mode (response_format={"type":"json_object"}) garante schema.
- Circuit Breaker: 3 falhas consecutivas → cooldown 60-300s (backoff 1.5x).
- 429 ABRE circuit do provider (evita martelar free-tier esgotado).
- Session-level exhaustion: se TODOS providers falham → flag "LLM esgotado"
  pro resto do scrape → review_queue direto, sem latência.
- Try/except robusto: timeout, rate limit, erro de rede → todos capturados.
"""

import httpx
import json
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, cast

from services.http_client import get_client
from services.logger import logger

from services.rate_limiter import TokenBucket, TokenBucketConfig

CIRCUIT_FAILURE_THRESHOLD = int(os.environ.get("LLM_CB_THRESHOLD", "3"))
CIRCUIT_COOLDOWN_SECONDS = int(os.environ.get("LLM_CB_COOLDOWN", "60"))  # 60s (nao 600)
CIRCUIT_COOLDOWN_MAX = int(os.environ.get("LLM_CB_COOLDOWN_MAX", "300"))  # 5min max
CIRCUIT_COOLDOWN_GROWTH = float(os.environ.get("LLM_CB_COOLDOWN_GROWTH", "1.5"))
DEFAULT_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "15"))
# TokenBucket por provider: 30 RPM default
TOKEN_BUCKET_RATE = float(os.environ.get("LLM_RATE_LIMIT", "30"))
TOKEN_BUCKET_CAPACITY = float(os.environ.get("LLM_BURST", "30"))


def _get_cooldown_seconds() -> int:
    """Read cooldown dynamically so tests using monkeypatch.setenv work correctly."""
    return int(os.environ.get("LLM_CB_COOLDOWN", str(CIRCUIT_COOLDOWN_SECONDS)))


def _get_cooldown_max() -> int:
    return int(os.environ.get("LLM_CB_COOLDOWN_MAX", str(CIRCUIT_COOLDOWN_MAX)))


def _get_cooldown_growth() -> float:
    return float(os.environ.get("LLM_CB_COOLDOWN_GROWTH", str(CIRCUIT_COOLDOWN_GROWTH)))


def _get_failure_threshold() -> int:
    """Read threshold dynamically so tests using monkeypatch.setenv work correctly."""
    return int(os.environ.get("LLM_CB_THRESHOLD", str(CIRCUIT_FAILURE_THRESHOLD)))


# Session-level LLM exhaustion flag (thread-safe)
# Quando TODOS os providers configurados falham, seta True pro resto do scrape.
# Evita chamar LLM pro resto da coleta -> review_queue direto, sem latencia.
_LLM_EXHAUSTED = False
_LLM_EXHAUSTED_LOCK = threading.Lock()


def reset_llm_exhausted() -> None:
    """Chamar no INICIO de cada scrape (main.py / collector)."""
    global _LLM_EXHAUSTED
    with _LLM_EXHAUSTED_LOCK:
        _LLM_EXHAUSTED = False


def _is_llm_exhausted() -> bool:
    """Checar se LLM já esgotou nessa sessao."""
    with _LLM_EXHAUSTED_LOCK:
        return _LLM_EXHAUSTED


def _set_llm_exhausted(value: bool) -> None:
    """Marcar LLM como esgotado pro resto da sessao."""
    global _LLM_EXHAUSTED
    with _LLM_EXHAUSTED_LOCK:
        _LLM_EXHAUSTED = value


@dataclass
class LLMResult:
    match: bool
    canonical_name: str
    confidence_score: float
    reason: str
    provider: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open for a provider."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"Circuit breaker open for provider '{provider}'")
        self.provider = provider


class LLMStrategy(ABC):
    """Abstract base class for LLM providers."""

    provider_name: str = "abstract"

    def __init__(self, provider_name: str | None = None) -> None:
        if provider_name is not None:
            self.provider_name = provider_name
        self.failure_count = 0
        self.last_failure_ts: float = 0.0
        self._cooldown_seconds = _get_cooldown_seconds()
        self._consecutive_openings = 0
        self._token_bucket: TokenBucket = TokenBucket(
            TokenBucketConfig(
                capacity=TOKEN_BUCKET_CAPACITY,
                refill_rate=TOKEN_BUCKET_RATE / 60.0,
            )
        )

    def _check_rate_limit(self) -> bool:
        """Proactive rate limiting via TokenBucket. Returns False if throttled."""
        if not self._token_bucket.consume(self.provider_name):
            wait = self._token_bucket.wait_time(self.provider_name)
            if wait > 1.0:
                logger.info("[%s] Rate limited (TokenBucket), waiting %.1fs", self.provider_name, wait)
            time.sleep(wait)
            return self._token_bucket.consume(self.provider_name)
        return True

    @abstractmethod
    def classify(self, product_text: str, candidates: list[dict[str, Any]]) -> LLMResult | None:
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """True if this provider has credentials / configuration available."""
        pass

    def is_circuit_open(self) -> bool:
        """Returns True if the circuit breaker should be treated as open.

        Circuit abre em 3 falhas consecutivas. Cooldown: 60s base, backoff 1.5x,
        max 300s. Ao expirar, permite UMA tentativa (half-open). Se falhar de novo
        (429/500), reabre com cooldown maior.
        """
        threshold = _get_failure_threshold()
        if self.failure_count < threshold:
            return False
        elapsed = time.time() - self.last_failure_ts
        # Cooldown não expirou -> aberto. Ao expirar, permite UMA tentativa
        # (half-open); o contador só zera de fato em record_success(). Se falhar
        # de novo (429/500), open_circuit reabre com cooldown maior (backoff).
        return elapsed < self._cooldown_seconds

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_ts = time.time()

    def record_success(self) -> None:
        self.failure_count = 0
        self._consecutive_openings = 0
        self._cooldown_seconds = _get_cooldown_seconds()

    def open_circuit(self) -> None:
        """Abre o breaker para 429/500/503/timeout.

        429 AGORA ABRE circuit -- provider esgotou quota, nao adianta martelar.
        Cooldown: 60s base, backoff 1.5x a cada reabertura, max 300s.
        """
        self.failure_count = _get_failure_threshold()
        self.last_failure_ts = time.time()
        self._consecutive_openings += 1
        growth = _get_cooldown_growth()
        base = _get_cooldown_seconds()
        new_cooldown = min(base * (growth**self._consecutive_openings), _get_cooldown_max())
        self._cooldown_seconds = int(max(base, new_cooldown))
        logger.warning(
            "[%s] Circuit breaker OPEN cooldown=%ds",
            self.provider_name,
            self._cooldown_seconds,
        )

    def _handle_429(self, response: httpx.Response) -> None:
        """429: abre circuit e fallthrough. NAO faz retry interno."""
        logger.info("[%s] 429 rate limited, opening circuit (fallthrough)", self.provider_name)
        self.open_circuit()
        return None

    def _safe_api_call(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> httpx.Response | None:
        """Unified API call with TokenBucket + 429->circuit + Circuit Breaker.

        Returns response on success (2xx), None on fallthrough (429/500/timeout).
        Opens circuit on 429/500/503/timeout.
        """
        # Early exit: LLM esgotado nesta sessao
        if _is_llm_exhausted():
            logger.debug("[%s] LLM exhausted flag set, skipping", self.provider_name)
            return None

        if not self._check_rate_limit():
            logger.debug("[%s] TokenBucket exhausted, skipping", self.provider_name)
            return None

        try:
            resp: httpx.Response = get_client().post(url, headers=headers, json=payload, params=params, timeout=DEFAULT_TIMEOUT)

            if resp.status_code == 429:
                self._handle_429(resp)
                return None

            if resp.status_code >= 500:
                logger.warning("[%s] HTTP %s server error, opening circuit", self.provider_name, resp.status_code)
                self.open_circuit()
                return None

            if resp.status_code >= 400:
                logger.warning("[%s] HTTP %s client error, opening circuit", self.provider_name, resp.status_code)
                self.open_circuit()
                return None

            return resp

        except httpx.TimeoutException:
            logger.warning("[%s] timeout, opening circuit", self.provider_name)
            self.open_circuit()
            return None
        except httpx.NetworkError:
            logger.warning("[%s] network error, opening circuit", self.provider_name)
            self.open_circuit()
            return None
        except Exception as e:
            logger.warning("[%s] API call error: %s", self.provider_name, e)
            self.record_failure()
            return None

    def _safe_parse(self, content: str) -> dict[str, Any] | None:
        """Parses JSON content robustly, handling markdown fences and malformed responses."""
        if not content:
            return None
        # Strip markdown code fences if present
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        # Try to find JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
            return cast(dict[str, Any], parsed)
        except Exception:
            return None


class GroqStrategy(LLMStrategy):
    provider_name = "groq"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def classify(self, product_text: str, candidates: list[dict[str, Any]]) -> LLMResult | None:
        if not self.api_key:
            logger.debug("groq_skipped_no_api_key")
            return None
        if self.is_circuit_open():
            logger.debug("groq_circuit_open")
            return None

        candidates_str = "\n".join(
            f"- {c.get('canonical_name', '?')} (aliases: {', '.join(c.get('aliases', []))})" for c in candidates
        )
        system_prompt = (
            "Você é um classificador de ingredientes para confeitaria analítica e metódica. "
            "Analise o produto e decida se corresponde a algum dos ingredientes listados. "
            "Responda APENAS com JSON válido (sem markdown, sem texto extra) no schema: "
            '{"match": boolean, "canonical_name": string, "confidence_score": float entre 0 e 1, "reason": string}. '
            "Se nenhum ingrediente corresponder, retorne match=false."
        )
        user_prompt = f"Produto: {product_text}\n\nIngredientes candidatos:\n{candidates_str}"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 200,
            "response_format": {"type": "json_object"},
        }
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = self._safe_api_call(self.url, headers, payload)
            if resp is None:
                return None

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._safe_parse(content)

            if not parsed:
                logger.warning("groq_invalid_json_response")
                self.record_failure()
                return None
            self.record_success()
            return LLMResult(
                match=bool(parsed.get("match", False)),
                canonical_name=str(parsed.get("canonical_name") or ""),
                confidence_score=float(parsed.get("confidence_score") or 0.0),
                reason=str(parsed.get("reason", "")),
                provider="groq",
            )
        except Exception as e:
            logger.warning("groq_unexpected_error", error=str(e))
            self.record_failure()
            return None


class OpenRouterStrategy(LLMStrategy):
    provider_name = "openrouter"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = os.environ.get("OPENROUTER_MODEL", "openrouter/free")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def classify(self, product_text: str, candidates: list[dict[str, Any]]) -> LLMResult | None:
        if not self.api_key:
            logger.debug("openrouter_skipped_no_api_key")
            return None
        if self.is_circuit_open():
            logger.debug("openrouter_circuit_open")
            return None

        candidates_str = "\n".join(f"- {c.get('canonical_name', '?')}" for c in candidates)
        prompt = (
            "Classify this product vs candidate ingredients. Respond ONLY with JSON: "
            '{"match": bool, "canonical_name": str, "confidence_score": float, "reason": str}\n\n'
            f"Product: {product_text}\nCandidates:\n{candidates_str}"
        )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = self._safe_api_call(self.url, headers, payload)
            if resp is None:
                return None

            data = resp.json()
            if isinstance(data, dict) and "error" in data and "choices" not in data:
                logger.warning("openrouter_api_error", error=str(data["error"]))
                self.open_circuit()
                return None
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._safe_parse(content)
            if not parsed:
                logger.warning("openrouter_invalid_json_response")
                self.record_failure()
                return None
            self.record_success()
            return LLMResult(
                match=bool(parsed.get("match", False)),
                canonical_name=str(parsed.get("canonical_name") or ""),
                confidence_score=float(parsed.get("confidence_score") or 0.0),
                reason=str(parsed.get("reason", "")),
                provider="openrouter",
            )
        except Exception as e:
            logger.warning("openrouter_error", error=str(e))
            self.record_failure()
            return None


# ====================================================================
# End of file - only Groq and OpenRouter strategies remain
# (Other providers removed to reduce 429 rate limit issues)
# ====================================================================
