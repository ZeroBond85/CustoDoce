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

    def __init__(self, provider_name: str | None = None):
        if provider_name is not None:
            self.provider_name = provider_name
        self.failure_count = 0
        self.last_failure_ts: float = 0.0
        self._cooldown_seconds = _get_cooldown_seconds()
        self._consecutive_openings = 0
        self._token_bucket = TokenBucket(
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

    def _smart_429(self, response) -> bool:
        """Handle 429: retry ONCE with Retry-After, then fall through. Returns True if caller should retry."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = float(retry_after)
                logger.info("[%s] 429 Retry-After=%ss, waiting then retrying once", self.provider_name, delay)
                time.sleep(min(delay, 30.0))
                return True
            except (TypeError, ValueError):
                pass
        return False

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
        """Abre o breaker para 500/503/timeout (erros de servidor/rede).

        429 NAO abre circuit — apenas fallthrough para proximo provider.
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
            "[%s] Circuit breaker OPEN (server error) cooldown=%ds",
            self.provider_name,
            self._cooldown_seconds,
        )

    def _handle_429(self, response) -> None:
        """429: smart retry ONCE, then fall through. NEVER opens circuit."""
        retry_after = response.headers.get("Retry-After", "")
        try:
            delay = min(float(retry_after), 30.0) if retry_after else 5.0
        except (TypeError, ValueError):
            delay = 5.0
        logger.info("[%s] 429 rate limited, retrying once after %.1fs", self.provider_name, delay)
        time.sleep(delay)
        # Do NOT open circuit — 429 is transient, next provider in chain handles it

    def _safe_api_call(self, url: str, headers: dict, payload: dict, params: dict | None = None) -> httpx.Response | None:
        """Unified API call with TokenBucket + Smart 429 + Circuit Breaker.

        Returns response on success (2xx), None on fallthrough (429/error).
        Opens circuit only on 500/503/timeout.
        """
        if not self._check_rate_limit():
            logger.debug("[%s] TokenBucket exhausted, skipping", self.provider_name)
            return None

        try:
            resp = get_client().post(url, headers=headers, json=payload, params=params, timeout=DEFAULT_TIMEOUT)

            if resp.status_code == 429:
                retried = self._smart_429(resp)
                if retried:
                    resp2 = get_client().post(url, headers=headers, json=payload, params=params, timeout=DEFAULT_TIMEOUT)
                    if resp2.status_code == 429:
                        logger.info("[%s] 429 after retry, falling through", self.provider_name)
                        return None
                    resp = resp2
                else:
                    return None

            if resp.status_code >= 400:
                logger.warning("[%s] HTTP %s error, opening circuit", self.provider_name, resp.status_code)
                self.open_circuit()
                return None

            return resp

        except httpx.TimeoutException:
            logger.warning("[%s] timeout", self.provider_name)
            self.open_circuit()
            return None
        except httpx.NetworkError:
            logger.warning("[%s] network error, opening circuit", self.provider_name)
            self.open_circuit()
            return None
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429:
                retried = self._smart_429(e.response)
                if retried:
                    try:
                        resp2 = get_client().post(url, headers=headers, json=payload, params=params, timeout=DEFAULT_TIMEOUT)
                        resp2.raise_for_status()
                        return resp2
                    except httpx.HTTPStatusError as e2:
                        if e2.response.status_code == 429:
                            logger.info("[%s] 429 after retry, falling through", self.provider_name)
                            return None
                        self.record_failure()
                        return None
                    except Exception:
                        self.record_failure()
                        return None
                return None
            if status >= 400 and status != 429:
                logger.warning("[%s] HTTP %s client error, opening circuit", self.provider_name, status)
                self.open_circuit()
                return None
            logger.warning("[%s] HTTP error %s", self.provider_name, e)
            self.record_failure()
            return None
        except Exception as e:
            logger.warning("[%s] API call error: %s", self.provider_name, e)
            self.record_failure()
            return None

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
            resp = self._safe_api_call(url, headers, payload)
            if resp is None:
                return None

            data = resp.json()
            if isinstance(data, dict) and "error" in data and "choices" not in data:
                logger.warning("huggingface_api_error", error=str(data["error"]))
                self.open_circuit()
                return None
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
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


# ====================================================================
# Additional Provider Strategies (completing the 9-provider chain)
# ====================================================================

class GoogleStrategy(LLMStrategy):
    """Google Gemini strategy."""

    def __init__(self):
        super().__init__("google")
        self.url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        self.api_key = os.environ.get("GOOGLE_API_KEY", "")
        self.headers = {"Content-Type": "application/json"}

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def classify(self, product_text: str, candidates: list) -> LLMResult | None:
        if not self.api_key:
            logger.debug("google_skipped_no_api_key")
            return None
        if self.is_circuit_open():
            logger.debug("google_circuit_open")
            return None

        prompt = self._build_prompt(product_text, candidates)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        params = {"key": self.api_key}

        try:
            params = {"key": self.api_key}
            resp = self._safe_api_call(self.url, self.headers, payload, params=params)
            if resp is None:
                return None

            data = resp.json()
            content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            parsed = self._safe_parse(content)
            if not parsed:
                logger.warning("google_invalid_json_response")
                self.record_failure()
                return None
            self.record_success()
            return LLMResult(
                match=bool(parsed.get("match", False)),
                canonical_name=str(parsed.get("canonical_name") or ""),
                confidence_score=float(parsed.get("confidence_score") or 0.0),
                reason=str(parsed.get("reason", "")),
                provider="google",
            )
        except Exception as e:
            logger.warning("google_error", error=str(e))
            self.record_failure()
            return None

    def _build_prompt(self, product_text: str, candidates: list) -> str:
        candidates_str = "\n".join(
            f"- {c.get('canonical_name', '?')} (aliases: {', '.join(c.get('aliases', []))})" for c in candidates
        )
        return (
            "Você é um classificador de ingredientes para confeitaria analítica e metódica. "
            "Analise o produto e decida se corresponde a algum dos ingredientes listados. "
            "Responda APENAS com JSON válido (sem markdown, sem texto extra) no schema: "
            '{"match": boolean, "canonical_name": string, "confidence_score": float entre 0 e 1, "reason": string}. '
            "Se nenhum ingrediente corresponder, retorne match=false.\n\n"
            f"Produto: {product_text}\n\nIngredientes candidatos:\n{candidates_str}"
        )


class OpenAIStrategy(LLMStrategy):
    """OpenAI GPT strategy."""

    def __init__(self):
        super().__init__("openai")
        self.url = "https://api.openai.com/v1/chat/completions"
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def classify(self, product_text: str, candidates: list) -> LLMResult | None:
        if not self.api_key:
            logger.debug("openai_skipped_no_api_key")
            return None
        if self.is_circuit_open():
            logger.debug("openai_circuit_open")
            return None

        prompt = self._build_prompt(product_text, candidates)
        payload = {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        try:
            resp = self._safe_api_call(self.url, self.headers, payload)
            if resp is None:
                return None

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._safe_parse(content)
            if not parsed:
                logger.warning("openai_invalid_json_response")
                self.record_failure()
                return None
            self.record_success()
            return LLMResult(
                match=bool(parsed.get("match", False)),
                canonical_name=str(parsed.get("canonical_name") or ""),
                confidence_score=float(parsed.get("confidence_score") or 0.0),
                reason=str(parsed.get("reason", "")),
                provider="openai",
            )
        except Exception as e:
            logger.warning("openai_error", error=str(e))
            self.record_failure()
            return None

    def _build_prompt(self, product_text: str, candidates: list) -> str:
        candidates_str = "\n".join(
            f"- {c.get('canonical_name', '?')} (aliases: {', '.join(c.get('aliases', []))})" for c in candidates
        )
        return (
            "Você é um classificador de ingredientes para confeitaria analítica e metódica. "
            "Analise o produto e decida se corresponde a algum dos ingredientes listados. "
            "Responda APENAS com JSON válido (sem markdown, sem texto extra) no schema: "
            '{"match": boolean, "canonical_name": string, "confidence_score": float entre 0 e 1, "reason": string}. '
            "Se nenhum ingrediente corresponder, retorne match=false.\n\n"
            f"Produto: {product_text}\n\nIngredientes candidatos:\n{candidates_str}"
        )


class MistralStrategy(LLMStrategy):
    """Mistral AI strategy."""

    def __init__(self):
        super().__init__("mistral")
        self.url = "https://api.mistral.ai/v1/chat/completions"
        self.api_key = os.environ.get("MISTRAL_API_KEY", "")
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def classify(self, product_text: str, candidates: list) -> LLMResult | None:
        if not self.api_key:
            logger.debug("mistral_skipped_no_api_key")
            return None
        if self.is_circuit_open():
            logger.debug("mistral_circuit_open")
            return None

        prompt = self._build_prompt(product_text, candidates)
        payload = {
            "model": os.environ.get("MISTRAL_MODEL", "mistral-small-latest"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        try:
            resp = self._safe_api_call(self.url, self.headers, payload)
            if resp is None:
                return None

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._safe_parse(content)
            if not parsed:
                logger.warning("mistral_invalid_json_response")
                self.record_failure()
                return None
            self.record_success()
            return LLMResult(
                match=bool(parsed.get("match", False)),
                canonical_name=str(parsed.get("canonical_name") or ""),
                confidence_score=float(parsed.get("confidence_score") or 0.0),
                reason=str(parsed.get("reason", "")),
                provider="mistral",
            )
        except Exception as e:
            logger.warning("mistral_error", error=str(e))
            self.record_failure()
            return None


    def _build_prompt(self, product_text: str, candidates: list) -> str:
        candidates_str = "\n".join(
            f"- {c.get('canonical_name', '?')} (aliases: {', '.join(c.get('aliases', []))})" for c in candidates
        )
        return (
            "Você é um classificador de ingredientes para confeitaria analítica e metódica. "
            "Analise o produto e decida se corresponde a algum dos ingredientes listados. "
            "Responda APENAS com JSON válido (sem markdown, sem texto extra) no schema: "
            '{"match": boolean, "canonical_name": string, "confidence_score": float entre 0 e 1, "reason": string}. '
            "Se nenhum ingrediente corresponder, retorne match=false.\n\n"
            f"Produto: {product_text}\n\nIngredientes candidatos:\n{candidates_str}"
        )


class DeepSeekStrategy(LLMStrategy):
    """DeepSeek strategy."""

    def __init__(self):
        super().__init__("deepseek")
        self.url = "https://api.deepseek.com/v1/chat/completions"
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def classify(self, product_text: str, candidates: list) -> LLMResult | None:
        if not self.api_key:
            logger.debug("deepseek_skipped_no_api_key")
            return None
        if self.is_circuit_open():
            logger.debug("deepseek_circuit_open")
            return None

        prompt = self._build_prompt(product_text, candidates)
        payload = {
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        try:
            resp = self._safe_api_call(self.url, self.headers, payload)
            if resp is None:
                return None

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._safe_parse(content)
            if not parsed:
                logger.warning("deepseek_invalid_json_response")
                self.record_failure()
                return None
            self.record_success()
            return LLMResult(
                match=bool(parsed.get("match", False)),
                canonical_name=str(parsed.get("canonical_name") or ""),
                confidence_score=float(parsed.get("confidence_score") or 0.0),
                reason=str(parsed.get("reason", "")),
                provider="deepseek",
            )
        except Exception as e:
            logger.warning("deepseek_error", error=str(e))
            self.record_failure()
            return None


    def _build_prompt(self, product_text: str, candidates: list) -> str:
        candidates_str = "\n".join(
            f"- {c.get('canonical_name', '?')} (aliases: {', '.join(c.get('aliases', []))})" for c in candidates
        )
        return (
            "Você é um classificador de ingredientes para confeitaria analítica e metódica. "
            "Analise o produto e decida se corresponde a algum dos ingredientes listados. "
            "Responda APENAS com JSON válido (sem markdown, sem texto extra) no schema: "
            '{"match": boolean, "canonical_name": string, "confidence_score": float entre 0 e 1, "reason": string}. '
            "Se nenhum ingrediente corresponder, retorne match=false.\n\n"
            f"Produto: {product_text}\n\nIngredientes candidatos:\n{candidates_str}"
        )


class NVIDIAStrategy(LLMStrategy):
    """NVIDIA NIM strategy."""

    def __init__(self):
        super().__init__("nvidia")
        self.url = "https://integrate.api.nvidia.com/v1/chat/completions"
        self.api_key = os.environ.get("NVIDIA_API_KEY", "")
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def classify(self, product_text: str, candidates: list) -> LLMResult | None:
        if not self.api_key:
            logger.debug("nvidia_skipped_no_api_key")
            return None
        if self.is_circuit_open():
            logger.debug("nvidia_circuit_open")
            return None

        prompt = self._build_prompt(product_text, candidates)
        payload = {
            "model": os.environ.get("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        try:
            resp = self._safe_api_call(self.url, self.headers, payload)
            if resp is None:
                return None

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._safe_parse(content)
            if not parsed:
                logger.warning("nvidia_invalid_json_response")
                self.record_failure()
                return None
            self.record_success()
            return LLMResult(
                match=bool(parsed.get("match", False)),
                canonical_name=str(parsed.get("canonical_name") or ""),
                confidence_score=float(parsed.get("confidence_score") or 0.0),
                reason=str(parsed.get("reason", "")),
                provider="nvidia",
            )
        except Exception as e:
            logger.warning("nvidia_error", error=str(e))
            self.record_failure()
            return None


    def _build_prompt(self, product_text: str, candidates: list) -> str:
        candidates_str = "\n".join(
            f"- {c.get('canonical_name', '?')} (aliases: {', '.join(c.get('aliases', []))})" for c in candidates
        )
        return (
            "Você é um classificador de ingredientes para confeitaria analítica e metódica. "
            "Analise o produto e decida se corresponde a algum dos ingredientes listados. "
            "Responda APENAS com JSON válido (sem markdown, sem texto extra) no schema: "
            '{"match": boolean, "canonical_name": string, "confidence_score": float entre 0 e 1, "reason": string}. '
            "Se nenhum ingrediente corresponder, retorne match=false.\n\n"
            f"Produto: {product_text}\n\nIngredientes candidatos:\n{candidates_str}"
        )


class GitHubModelsStrategy(LLMStrategy):
    """GitHub Models strategy (via GitHub Models API)."""

    def __init__(self):
        super().__init__("github_models")
        self.url = "https://models.inference.ai.azure.com/chat/completions"
        self.api_key = os.environ.get("GH_MODELS_TOKEN", "")
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def classify(self, product_text: str, candidates: list) -> LLMResult | None:
        if not self.api_key:
            logger.debug("github_models_skipped_no_api_key")
            return None
        if self.is_circuit_open():
            logger.debug("github_models_circuit_open")
            return None

        prompt = self._build_prompt(product_text, candidates)
        payload = {
            "model": os.environ.get("GITHUB_MODELS_MODEL", "gpt-4o-mini"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        try:
            resp = self._safe_api_call(self.url, self.headers, payload)
            if resp is None:
                return None

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._safe_parse(content)
            if not parsed:
                logger.warning("github_models_invalid_json_response")
                self.record_failure()
                return None
            self.record_success()
            return LLMResult(
                match=bool(parsed.get("match", False)),
                canonical_name=str(parsed.get("canonical_name") or ""),
                confidence_score=float(parsed.get("confidence_score") or 0.0),
                reason=str(parsed.get("reason", "")),
                provider="github_models",
            )
        except Exception as e:
            logger.warning("github_models_error", error=str(e))
            self.record_failure()
            return None

    def _build_prompt(self, product_text: str, candidates: list) -> str:
        candidates_str = "\n".join(
            f"- {c.get('canonical_name', '?')} (aliases: {', '.join(c.get('aliases', []))})" for c in candidates
        )
        return (
            "Você é um classificador de ingredientes para confeitaria analítica e metódica. "
            "Analise o produto e decida se corresponde a algum dos ingredientes listados. "
            "Responda APENAS com JSON válido (sem markdown, sem texto extra) no schema: "
            '{"match": boolean, "canonical_name": string, "confidence_score": float entre 0 e 1, "reason": string}. '
            "Se nenhum ingrediente corresponder, retorne match=false.\n\n"
            f"Produto: {product_text}\n\nIngredientes candidatos:\n{candidates_str}"
        )
