"""
LLM Strategy Pattern com Circuit Breaker e JSON Mode.

Objetivo (RFC Recurso 2): Evitar crashes do pipeline quando APIs externas caem.
- Cada provider implementa o mesmo contrato (LLMStrategy ABC).
- Tenta Groq (primário) → OpenRouter (fallback 1) → HuggingFace (fallback 2).
- JSON Mode (response_format={"type":"json_object"}) garante schema.
- Circuit Breaker simples: 3 falhas consecutivas → desliga o provider por 10 min.
- Try/except robusto: timeout, rate limit, erro de rede → todos capturados.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
import os
import json
import time

import httpx

from services.logger import logger

CIRCUIT_FAILURE_THRESHOLD = int(os.environ.get("LLM_CB_THRESHOLD", "3"))
CIRCUIT_COOLDOWN_SECONDS = int(os.environ.get("LLM_CB_COOLDOWN", "600"))  # 10 min
DEFAULT_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "15"))


def _get_cooldown_seconds() -> int:
    """Read cooldown dynamically so tests using monkeypatch.setenv work correctly."""
    return int(os.environ.get("LLM_CB_COOLDOWN", str(CIRCUIT_COOLDOWN_SECONDS)))


def _get_failure_threshold() -> int:
    """Read threshold dynamically so tests using monkeypatch.setenv work correctly."""
    return int(os.environ.get("LLM_CB_THRESHOLD", str(CIRCUIT_FAILURE_THRESHOLD)))


@dataclass
class LLMResult:
    match: bool
    canonical_name: str
    confidence_score: float
    reason: str
    provider: str

    def to_dict(self) -> dict:
        return asdict(self)


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open for a provider."""

    def __init__(self, provider: str):
        super().__init__(f"Circuit breaker open for provider '{provider}'")
        self.provider = provider


class LLMStrategy(ABC):
    """Abstract base class for LLM providers."""

    provider_name: str = "abstract"

    def __init__(self):
        self.failure_count = 0
        self.last_failure_ts: float = 0.0

    @abstractmethod
    def classify(self, product_text: str, candidates: list) -> LLMResult | None: ...

    @abstractmethod
    def is_configured(self) -> bool:
        """True if this provider has credentials / configuration available."""

        return True

    def is_circuit_open(self) -> bool:
        """Returns True if the circuit breaker should be treated as open."""
        threshold = _get_failure_threshold()
        if self.failure_count < threshold:
            return False
        elapsed = time.time() - self.last_failure_ts
        if elapsed < _get_cooldown_seconds():
            return True
        # Cooldown expired — reset so we try once
        self.failure_count = 0
        return False

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_ts = time.time()

    def record_success(self) -> None:
        self.failure_count = 0

    def _safe_parse(self, content: str) -> dict | None:
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
            return json.loads(text[start : end + 1])
        except Exception:
            return None


class GroqStrategy(LLMStrategy):
    provider_name = "groq"

    def __init__(self):
        super().__init__()
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def classify(self, product_text: str, candidates: list) -> LLMResult | None:
        if not self.api_key:
            logger.debug("groq_skipped_no_api_key")
            return None
        if self.is_circuit_open():
            logger.warning("groq_circuit_open")
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
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 200,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                resp = client.post(self.url, headers=headers, json=payload)

            if resp.status_code == 429:
                logger.warning("groq_rate_limited", status=429)
                self.record_failure()
                return None
            if resp.status_code >= 500:
                logger.warning("groq_server_error", status=resp.status_code)
                self.record_failure()
                return None
            resp.raise_for_status()
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
        except httpx.TimeoutException:
            logger.warning("groq_timeout")
            self.record_failure()
            return None
        except httpx.HTTPError as e:
            logger.warning("groq_http_error", error=str(e))
            self.record_failure()
            return None
        except Exception as e:
            logger.warning("groq_unexpected_error", error=str(e))
            self.record_failure()
            return None


class OpenRouterStrategy(LLMStrategy):
    provider_name = "openrouter"

    def __init__(self):
        super().__init__()
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = os.environ.get("OPENROUTER_MODEL", "mistralai/mixtral-8x7b-instruct")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def classify(self, product_text: str, candidates: list) -> LLMResult | None:
        if not self.api_key:
            logger.debug("openrouter_skipped_no_api_key")
            return None
        if self.is_circuit_open():
            logger.warning("openrouter_circuit_open")
            return None

        candidates_str = "\n".join(f"- {c.get('canonical_name', '?')}" for c in candidates)
        prompt = (
            "Classify this product vs candidate ingredients. Respond ONLY with JSON: "
            '{"match": bool, "canonical_name": str, "confidence_score": float, "reason": str}\n\n'
            f"Product: {product_text}\nCandidates:\n{candidates_str}"
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                resp = client.post(self.url, headers=headers, json=payload)
            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning("openrouter_retryable_error", status=resp.status_code)
                self.record_failure()
                return None
            resp.raise_for_status()
            data = resp.json()
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


class HuggingFaceStrategy(LLMStrategy):
    provider_name = "huggingface"

    def __init__(self):
        super().__init__()
        self.api_key = os.environ.get("HUGGINGFACE_API_KEY", "")
        self.model = os.environ.get("HUGGINGFACE_MODEL", "mistralai/Mistral-7B-Instruct-v0.2")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def classify(self, product_text: str, candidates: list) -> LLMResult | None:
        if not self.api_key:
            logger.debug("huggingface_skipped_no_api_key")
            return None
        if self.is_circuit_open():
            logger.warning("huggingface_circuit_open")
            return None

        url = f"https://api-inference.huggingface.co/models/{self.model}/v1/chat/completions"
        candidates_str = ", ".join(c.get("canonical_name", "?") for c in candidates)
        prompt = (
            "You are an ingredient classifier. Respond ONLY with JSON using schema: "
            '{"match": bool, "canonical_name": str, "confidence_score": float, "reason": str}\n'
            f"Product: {product_text}. Candidates: {candidates_str}"
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 200,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning("huggingface_retryable_error", status=resp.status_code)
                self.record_failure()
                return None
            if resp.status_code == 401:
                # 401 not retryable
                logger.warning("huggingface_unauthorized")
                self.record_failure()
                return None
            resp.raise_for_status()
            data = resp.json()
            # HF chat-completions format mirrors OpenAI
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                # Fallback: text-generation endpoint
                content = data.get("generated_text", "")
            parsed = self._safe_parse(content)
            if not parsed:
                logger.warning("huggingface_invalid_json_response")
                self.record_failure()
                return None
            self.record_success()
            return LLMResult(
                match=bool(parsed.get("match", False)),
                canonical_name=str(parsed.get("canonical_name") or ""),
                confidence_score=float(parsed.get("confidence_score") or 0.0),
                reason=str(parsed.get("reason", "")),
                provider="huggingface",
            )
        except Exception as e:
            logger.warning("huggingface_error", error=str(e))
            self.record_failure()
            return None
