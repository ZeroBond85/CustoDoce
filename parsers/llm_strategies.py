"""
LLM Strategy Pattern com Circuit Breaker e JSON Mode.

Objetivo (RFC Recurso 2): Evitar crashes do pipeline quando APIs externas caem.
- Cada provider implementa o mesmo contrato (LLMStrategy ABC).
- Tenta Groq (primário) → OpenRouter (fallback 1) → HuggingFace (fallback 2).
- JSON Mode (response_format={"type":"json_object"}) garante schema.
- Circuit Breaker simples: 3 falhas consecutivas → desliga o provider por 10 min.
- Try/except robusto: timeout, rate limit, erro de rede → todos capturados.
"""

import httpx
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass

from services.http_client import get_client
from services.logger import logger

CIRCUIT_FAILURE_THRESHOLD = int(os.environ.get("LLM_CB_THRESHOLD", "3"))
CIRCUIT_COOLDOWN_SECONDS = int(os.environ.get("LLM_CB_COOLDOWN", "600"))  # 10 min
# Backoff agressivo: a cada reabertura do breaker (provider ainda limitado),
# o cooldown DOBRA até o teto — evita martelar um provider free-tier esgotado
# (ex.: Groq 429) e desperdiçar a janela de scrape em retries inúteis.
CIRCUIT_COOLDOWN_MAX = int(os.environ.get("LLM_CB_COOLDOWN_MAX", "3600"))  # 1h
CIRCUIT_COOLDOWN_GROWTH = float(os.environ.get("LLM_CB_COOLDOWN_GROWTH", "2.0"))
DEFAULT_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "15"))


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
        # Cooldown efetivo atual (cresce com backoff agressivo a cada reabertura).
        self._cooldown_seconds = _get_cooldown_seconds()
        # Quantas vezes o breaker já reabriu por exaustão (para o backoff).
        self._consecutive_openings = 0

    @abstractmethod
    def classify(self, product_text: str, candidates: list) -> LLMResult | None: ...

    @abstractmethod
    def is_configured(self) -> bool:
        """True if this provider has credentials / configuration available."""

        return True

    def is_circuit_open(self) -> bool:
        """Returns True if the circuit breaker should be treated as open.

        Ao expirar o cooldown, NÃO zera o contador cegamente: tenta UMA vez e,
        se o provider ainda estiver limitado, aplica backoff agressivo (cooldown
        crescente) em vez de reiniciar o ciclo de 3 falhas rápidas. Isso evita
        os centenas de warnings de 429 que ocorriam quando o free-tier do Groq
        fica esgotado por horas.
        """
        threshold = _get_failure_threshold()
        if self.failure_count < threshold:
            return False
        elapsed = time.time() - self.last_failure_ts
        # Cooldown não expirou → aberto. Ao expirar, permitimos UMA tentativa
        # (half-open); o contador só zera de fato em record_success(). Se falhar
        # de novo (429), open_circuit reabre com cooldown maior (backoff).
        return elapsed < self._cooldown_seconds

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_ts = time.time()

    def record_success(self) -> None:
        self.failure_count = 0
        self._consecutive_openings = 0
        self._cooldown_seconds = _get_cooldown_seconds()

    def open_circuit(self) -> None:
        """Abre o breaker IMEDIATAMENTE (usado em 429/rate-limit).

        Aplica backoff agressivo: a cada reabertura consecutiva, o cooldown dobra
        (capado em LLM_CB_COOLDOWN_MAX). Assim um provider free-tier esgotado é
        pulado por períodos cada vez maiores, cedendo aos providers seguintes da
        cadeia em vez de queimar a janela de scrape em retries 429.
        """
        self.failure_count = _get_failure_threshold()
        self.last_failure_ts = time.time()
        self._consecutive_openings += 1
        growth = _get_cooldown_growth()
        base = _get_cooldown_seconds()
        new_cooldown = min(base * (growth**self._consecutive_openings), _get_cooldown_max())
        # Arredonda para int e garante ao menos o cooldown base.
        self._cooldown_seconds = int(max(base, new_cooldown))
        logger.warning(
            "[%s] Circuit breaker OPEN (rate-limited, ceding to next provider) cooldown=%ds",
            self.provider_name,
            self._cooldown_seconds,
        )

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
            # Breaker aberto (provider limitado/indisponível): pulamos e cedemos
            # ao próximo da cadeia. É comportamento normal de degradação
            # graceful, não erro — logado em debug para não poluir o scrape.
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
            resp = get_client().post(self.url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)

            if resp.status_code == 429:
                logger.warning("groq_rate_limited", status=429)
                # Provider free-tier esgotado: abre o breaker e cede ao próximo
                # da cadeia (OpenRouter/HF) em vez de gastar a janela em retries.
                self.open_circuit()
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
        # `openrouter/free` roteia automaticamente para um modelo free disponivel
        # (filtra por structured outputs). Slugs fixos (ex.: mixtral-8x7b) sao
        # descontinuados e passam a retornar 404 silenciosamente.
        self.model = os.environ.get("OPENROUTER_MODEL", "openrouter/free")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def classify(self, product_text: str, candidates: list) -> LLMResult | None:
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
            resp = get_client().post(self.url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning("openrouter_retryable_error", status=resp.status_code)
                # 429 = provider globalmente limitado agora: abre o breaker e cede
                # ao próximo da cadeia (backoff agressivo evita martelar o limite).
                self.open_circuit()
                return None
            if resp.status_code >= 400:
                # 4xx persistente (ex.: 404 modelo inexistente/config quebrada):
                # abre o breaker para NAO martelar o endpoint a cada produto —
                # o erro nao se resolve em retry, so corrigindo a config.
                logger.warning("openrouter_client_error", status=resp.status_code)
                self.open_circuit()
                return None
            resp.raise_for_status()
            data = resp.json()
            # API error envelope (ex.: {"error": {...}}) — config/quota, nao parse pontual.
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
            logger.debug("huggingface_circuit_open")
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
            resp = get_client().post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning("huggingface_retryable_error", status=resp.status_code)
                # 429 = provider globalmente limitado agora: abre o breaker e cede
                # ao próximo da cadeia (backoff agressivo evita martelar o limite).
                self.open_circuit()
                return None
            if resp.status_code == 401:
                # 401 not retryable
                logger.warning("huggingface_unauthorized")
                self.record_failure()
                return None
            resp.raise_for_status()
            data = resp.json()
            # API error envelope — config/quota, cede imediatamente.
            if isinstance(data, dict) and "error" in data and "choices" not in data:
                logger.warning("huggingface_api_error", error=str(data["error"]))
                self.open_circuit()
                return None
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
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
            # DNS/resolucao/rede quebrada (ex.: getaddrinfo failed): host inalcançável
            # agora — abre o breaker e cede ao próximo da cadeia em vez de martelar
            # um host morto por 3 falhas lentas.
            logger.warning("huggingface_network_error", error=str(e))
            self.open_circuit()
            return None
        except Exception as e:
            logger.warning("huggingface_error", error=str(e))
            self.record_failure()
            return None
            return None
