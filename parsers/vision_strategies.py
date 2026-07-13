"""
parsers/vision_strategies.py

Vision LLM Strategy Pattern — extração de produtos de imagens de flyer via LLMs multimodais.

Fallback chain: GroqVisionStrategy → OpenRouterVisionStrategy → HFVisionStrategy
Cada strategy herda circuit breaker + JSON mode do padrão existente.
"""

import base64
import io
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from services.http_client import get_client
from services.logger import logger

DEFAULT_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "30"))
CB_THRESHOLD = int(os.environ.get("LLM_CB_THRESHOLD", "3"))
CB_COOLDOWN = int(os.environ.get("LLM_CB_COOLDOWN", "600"))
# Encartes graficos vem em altissima resolucao (~2245x3389) e estouram o limite
# de payload dos providers (413). Redimensionamos + recomprimimos para JPEG antes
# de enviar. Valores overridable por env para tuning sem redeploy.
VISION_MAX_DIM = int(os.environ.get("VISION_MAX_DIM", "1600"))
VISION_JPEG_QUALITY = int(os.environ.get("VISION_JPEG_QUALITY", "85"))
VISION_MAX_BYTES = int(os.environ.get("VISION_MAX_BYTES", "900000"))
# Retry em rate-limit (429): Groq free-tier limita requisicoes de vision.
VISION_MAX_RETRIES = int(os.environ.get("VISION_MAX_RETRIES", "2"))
VISION_RETRY_BASE = float(os.environ.get("VISION_RETRY_BASE", "2.0"))


def _downscale_image(image_bytes: bytes) -> bytes:
    """Redimensiona e recomprime imagem para caber no limite de payload do LLM.

    Retorna JPEG (RGB) com maior dimensao <= VISION_MAX_DIM e, se necessario,
    reduz a qualidade ate ficar sob VISION_MAX_BYTES. Se o Pillow falhar ou a
    imagem ja estiver pequena, devolve os bytes originais.
    """
    try:
        from PIL import Image
    except Exception:
        return image_bytes

    try:
        with Image.open(io.BytesIO(image_bytes)) as im:
            im = im.convert("RGB")
            longest = max(im.size)
            if longest > VISION_MAX_DIM:
                scale = VISION_MAX_DIM / longest
                new_size = (max(1, int(im.width * scale)), max(1, int(im.height * scale)))
                im = im.resize(new_size, Image.LANCZOS)

            quality = VISION_JPEG_QUALITY
            for _ in range(4):
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=quality, optimize=True)
                data = buf.getvalue()
                if len(data) <= VISION_MAX_BYTES or quality <= 40:
                    break
                quality -= 15
            # Se, apesar de tudo, ficou maior que o original, usa o original.
            return data if len(data) < len(image_bytes) or longest > VISION_MAX_DIM else image_bytes
    except Exception as exc:
        logger.debug("[vision] downscale falhou (%s), usando bytes originais", exc)
        return image_bytes


@dataclass
class VisionResult:
    products: list[dict]
    raw_text: str
    provider: str


class VisionStrategy(ABC):
    """Base class for vision LLM strategies with circuit breaker."""

    provider_name: str = "base"
    url: str = ""
    api_key: str = ""

    def __init__(self):
        self._failure_count = 0
        self._last_failure = 0.0
        self._circuit_open = False

    def record_failure(self):
        self._failure_count += 1
        self._last_failure = time.time()
        if self._failure_count >= CB_THRESHOLD:
            self._circuit_open = True
            logger.warning("[%s_vision] Circuit breaker OPEN after %d failures", self.provider_name, CB_THRESHOLD)

    def record_success(self):
        self._failure_count = 0
        self._circuit_open = False

    def is_available(self) -> bool:
        if self._circuit_open:
            if time.time() - self._last_failure > CB_COOLDOWN:
                logger.info("[%s_vision] Circuit breaker half-open (cooldown passed)", self.provider_name)
                self._circuit_open = False
                return True
            return False
        return True

    @abstractmethod
    def _get_payload(self, image_bytes: bytes) -> dict:
        pass

    @abstractmethod
    def _parse_response(self, response_text: str) -> VisionResult | None:
        pass

    def _retry_after(self, resp, attempt: int) -> float:
        """Segundos de espera antes do proximo retry (respeita Retry-After)."""
        header = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
        if header:
            try:
                return min(float(header), 30.0)
            except (TypeError, ValueError):
                pass
        return VISION_RETRY_BASE * (2**attempt)

    def extract(self, image_bytes: bytes) -> VisionResult | None:
        if not self.is_available():
            logger.debug("[%s_vision] Circuit breaker open, skipping", self.provider_name)
            return None

        for attempt in range(VISION_MAX_RETRIES + 1):
            try:
                payload = self._get_payload(image_bytes)
                headers = self._get_headers()

                resp = get_client().post(self.url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)

                if resp.status_code == 429:
                    if attempt < VISION_MAX_RETRIES:
                        wait = self._retry_after(resp, attempt)
                        logger.warning(
                            "[%s_vision] Rate limited, retry %d/%d em %.1fs",
                            self.provider_name, attempt + 1, VISION_MAX_RETRIES, wait,
                        )
                        time.sleep(wait)
                        continue
                    logger.warning("[%s_vision] Rate limited (retries esgotados)", self.provider_name)
                    self.record_failure()
                    return None
                if resp.status_code >= 500:
                    logger.warning("[%s_vision] Server error: %d", self.provider_name, resp.status_code)
                    self.record_failure()
                    return None
                resp.raise_for_status()

                data = resp.json()
                content = self._extract_content(data)
                result = self._parse_response(content)

                if result:
                    self.record_success()
                    result.provider = self.provider_name
                else:
                    logger.warning("[%s_vision] Invalid response format", self.provider_name)
                    self.record_failure()

                return result

            except Exception as e:
                logger.warning("[%s_vision] Error: %s", self.provider_name, e)
                self.record_failure()
                return None
        return None

    def _get_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _extract_content(self, data: dict) -> str:
        """Extrai o texto da resposta (formato OpenAI-compatible por padrao)."""
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    def _encode_image(self, image_bytes: bytes) -> str:
        return base64.b64encode(_downscale_image(image_bytes)).decode()


def _strip_json_fence(content: str) -> str:
    """Remove cercas markdown (```json ... ```) e isola o objeto JSON.

    Modelos free (OpenRouter/HF) frequentemente ignoram ``response_format`` e
    devolvem o JSON embrulhado em markdown ou com texto ao redor.
    """
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)
        text = text[1] if len(text) > 1 else content
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text.strip()


def _safe_parse(content: str) -> VisionResult | None:
    """Safely parse LLM JSON response into VisionResult."""
    if not content:
        return None
    for candidate in (content, _strip_json_fence(content)):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return VisionResult(
                products=data.get("products", []),
                raw_text=data.get("raw_text", ""),
                provider="",
            )
    logger.warning("[vision] Invalid JSON response")
    return None


class GroqVisionStrategy(VisionStrategy):
    provider_name = "groq"

    def __init__(self):
        super().__init__()
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = os.environ.get("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

    def _get_payload(self, image_bytes: bytes) -> dict:
        b64 = self._encode_image(image_bytes)
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extraia produtos deste flyer. Retorne JSON: {'products': [{'product': str, 'price': float, 'unit': str, 'validity': str}], 'raw_text': str}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
        }

    def _parse_response(self, content: str) -> VisionResult | None:
        return _safe_parse(content)


_VISION_PROMPT = (
    "Extraia produtos deste flyer. Retorne SOMENTE JSON: "
    '{"products": [{"product": str, "price": float, "unit": str, "validity": str}], "raw_text": str}'
)


class GeminiVisionStrategy(VisionStrategy):
    """Google Gemini (generativelanguage API) — formato de payload/resposta proprio."""

    provider_name = "gemini"

    def __init__(self):
        super().__init__()
        self.api_key = os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        self.model = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash-lite")
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

    def _get_payload(self, image_bytes: bytes) -> dict:
        b64 = self._encode_image(image_bytes)
        return {
            "contents": [
                {
                    "parts": [
                        {"text": _VISION_PROMPT},
                        {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json",
            },
        }

    def _get_headers(self) -> dict:
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def _extract_content(self, data: dict) -> str:
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return ""

    def _parse_response(self, content: str) -> VisionResult | None:
        return _safe_parse(content)


class OpenRouterVisionStrategy(VisionStrategy):
    provider_name = "openrouter"

    def __init__(self):
        super().__init__()
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = os.environ.get("OPENROUTER_VISION_MODEL", "google/gemma-4-31b-it:free")

    def _get_payload(self, image_bytes: bytes) -> dict:
        b64 = self._encode_image(image_bytes)
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extraia produtos deste flyer. Retorne JSON: {'products': [{'product': str, 'price': float, 'unit': str, 'validity': str}], 'raw_text': str}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
        }

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/anomalyco/custodoce",
        }

    def _parse_response(self, content: str) -> VisionResult | None:
        return _safe_parse(content)


class HFVisionStrategy(VisionStrategy):
    provider_name = "hf"

    def __init__(self):
        super().__init__()
        self.api_key = os.environ.get("HF_API_KEY", "") or os.environ.get("HUGGINGFACE_API_KEY", "")
        self.url = os.environ.get("HF_VISION_URL", "https://api-inference.huggingface.co/models/llava-hf/llava-1.5-7b-hf")

    def _get_payload(self, image_bytes: bytes) -> dict:
        b64 = self._encode_image(image_bytes)
        return {
            "inputs": {
                "text": "Extraia produtos deste flyer. Retorne JSON: {'products': [{'product': str, 'price': float, 'unit': str, 'validity': str}], 'raw_text': str}",
                "image": b64,
            },
            "parameters": {"max_new_tokens": 2000},
        }

    def _get_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _parse_response(self, content: str) -> VisionResult | None:
        if not content:
            return None
        try:
            # HF may return raw text, try to extract JSON
            data = json.loads(content)
            # HF sometimes returns list with generated_text
            if isinstance(data, list):
                content = data[0].get("generated_text", "")
            elif isinstance(data, dict):
                content = data.get("generated_text", content)

            return _safe_parse(content)
        except json.JSONDecodeError:
            logger.warning("[hf_vision] Invalid JSON response")
            return None


# Factory to get the fallback chain
def get_vision_chain() -> list[VisionStrategy]:
    """Return the vision strategy chain in fallback order."""
    return [
        GroqVisionStrategy(),
        GeminiVisionStrategy(),
        OpenRouterVisionStrategy(),
        HFVisionStrategy(),
    ]


def extract_products_via_vision(image_bytes: bytes) -> list[dict] | None:
    """Try each vision strategy in order until one succeeds."""
    for strategy in get_vision_chain():
        result = strategy.extract(image_bytes)
        if result and result.products:
            logger.info("[Vision] %s extracted %d products", strategy.provider_name, len(result.products))
            return result.products
    return None
