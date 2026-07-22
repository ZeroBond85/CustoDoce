"""
parsers/vision_strategies.py

Vision Strategy Pattern — extração de produtos de imagens de flyer.

Fallback chain: Gemini → NVIDIA → GitHub Models (GPT-4o) → OpenRouter → Tesseract.
Groq removido: nenhum modelo de visão disponível na API Groq.
Cada strategy herda circuit breaker + JSON mode do padrão existente.
"""

import base64
import io
import json
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
from PIL import Image

from services.http_client import get_client
from services.logger import logger

DEFAULT_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "90"))
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
# Em cadeia de fallback, um 429 significa "provider globalmente limitado agora":
# abrimos o circuit breaker e passamos para o proximo provider em vez de obedecer
# ao Retry-After (que queimava ~60s por imagem e estourava o timeout do scrape).
VISION_FAIL_FAST_ON_429 = os.environ.get("VISION_FAIL_FAST_ON_429", "1") not in ("0", "false", "False")


def _downscale_image(image_bytes: bytes) -> bytes:
    """Redimensiona e recomprime imagem para caber no limite de payload do LLM.

    Retorna JPEG (RGB) com maior dimensao <= VISION_MAX_DIM e, se necessario,
    reduz a qualidade ate ficar sob VISION_MAX_BYTES. Se o Pillow falhar ou a
    imagem ja estiver pequena, devolve os bytes originais.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as im_raw:
            im = im_raw.convert("RGB")
            longest = max(im.size)
            if longest > VISION_MAX_DIM:
                scale = VISION_MAX_DIM / longest
                new_size = (max(1, int(im.width * scale)), max(1, int(im.height * scale)))
                im = im.resize(new_size, Image.Resampling.LANCZOS)

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
    min_interval: float = 0.0
    timeout: float = 90.0

    def __init__(self):
        self._failure_count = 0
        self._last_failure = 0.0
        self._circuit_open = False
        self._last_request_time = 0.0
        # True se ha outro provider depois deste na cadeia (habilita fail-fast
        # em 429). Definido por get_vision_chain()/_get_cached_chain().
        self._has_fallback = False

    @property
    @abstractmethod
    def url(self) -> str: ...

    @property
    @abstractmethod
    def api_key(self) -> str: ...

    def record_failure(self):
        self._failure_count += 1
        self._last_failure = time.time()
        if self._failure_count >= CB_THRESHOLD:
            self._circuit_open = True
            logger.info("[%s_vision] Circuit breaker OPEN after %d failures", self.provider_name, CB_THRESHOLD)

    def open_circuit(self):
        """Abre o circuit breaker imediatamente (usado em 429 quando ha fallback)."""
        self._failure_count = CB_THRESHOLD
        self._circuit_open = True
        self._last_failure = time.time()
        logger.debug("[%s_vision] Circuit breaker OPEN (ceding to next provider)", self.provider_name)

    def record_success(self):
        self._failure_count = 0
        self._circuit_open = False



    def _throttle(self):
        if self.min_interval <= 0 or self._last_request_time <= 0:
            self._last_request_time = time.time()
            return
        elapsed = time.time() - self._last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        if self._circuit_open:
            if time.time() - self._last_failure > CB_COOLDOWN:
                logger.debug("[%s_vision] Circuit breaker half-open (cooldown passed)", self.provider_name)
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

                self._throttle()
                resp = get_client().post(self.url, headers=headers, json=payload, timeout=self.timeout)

                if resp.status_code == 429:
                    if VISION_FAIL_FAST_ON_429 and self._has_fallback:
                        self.open_circuit()
                        return None
                    if attempt < VISION_MAX_RETRIES:
                        wait = self._retry_after(resp, attempt)
                        logger.info(
                            "[%s_vision] Rate limited, retry %d/%d em %.1fs",
                            self.provider_name, attempt + 1, VISION_MAX_RETRIES, wait,
                        )
                        time.sleep(wait)
                        continue
                    logger.info("[%s_vision] Rate limited (retries exhausted)", self.provider_name)
                    self.record_failure()
                    return None
                if resp.status_code >= 500:
                    logger.warning("[%s_vision] Server error: %d", self.provider_name, resp.status_code)
                    self.record_failure()
                    return None
                if resp.status_code >= 400:
                    logger.warning("[%s_vision] Client error: %d — opening breaker", self.provider_name, resp.status_code)
                    self.open_circuit()
                    return None

                data = resp.json()
                content = self._extract_content(data)
                result = self._parse_response(content)

                if result:
                    self.record_success()
                    result.provider = self.provider_name
                else:
                    logger.info("[%s_vision] Invalid response format", self.provider_name)
                    self.record_failure()

                return result

            except httpx.TimeoutException:
                logger.debug("[%s_vision] Timeout (%.1fs)", self.provider_name, self.timeout)
                self.record_failure()
                return None
            except Exception as e:
                logger.info("[%s_vision] Error: %s", self.provider_name, e)
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
        parts = text.split("```", 2)
        text = parts[1] if len(parts) > 1 else content
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text.strip()


# Prompt unico e estrito: modelos free (NVIDIA/OpenRouter/Groq) ignoram
# response_format com frequencia e devolvem texto solto ou cercado em markdown.
# Pedir "ONLY raw JSON, no markdown" aumenta muito a taxa de parse valido.
_VISION_PROMPT = (
    "List the grocery products in this flyer. Respond with ONLY raw JSON "
    "(no markdown fences, no commentary): "
    '{"products": [{"product": string, "price": number, "unit": string}], "raw_text": string}'
)


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
    logger.debug("[vision] Invalid JSON response (ceding to next provider)")
    return None


class GroqVisionStrategy(VisionStrategy):
    provider_name = "groq"
    min_interval = 3.0  # 20 req/min max (segurado)

    def __init__(self):
        super().__init__()
        self._api_key = os.environ.get("GROQ_API_KEY", "")
        self._url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = os.environ.get("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def url(self) -> str:
        return self._url

    def _get_payload(self, image_bytes: bytes) -> dict:
        b64 = self._encode_image(image_bytes)
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 4000,
            "response_format": {"type": "json_object"},
        }

    def _parse_response(self, content: str) -> VisionResult | None:
        return _safe_parse(content)


class OpenRouterVisionStrategy(VisionStrategy):
    provider_name = "openrouter"
    timeout = 10.0

    def __init__(self):
        super().__init__()
        self._api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self._url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = os.environ.get("OPENROUTER_VISION_MODEL", "google/gemma-4-26b-a4b-it:free")

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def url(self) -> str:
        return self._url

    def _get_payload(self, image_bytes: bytes) -> dict:
        b64 = self._encode_image(image_bytes)
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 4000,
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


class NvidiaVisionStrategy(VisionStrategy):
    """NVIDIA NIM — modelos VLM hospedados (ex.: llama-3.2-11b-vision).

    Endpoint integrate.api.nvidia.com com model no payload (formato OpenAI).
    """

    provider_name = "nvidia"
    timeout = 10.0

    def __init__(self):
        super().__init__()
        self._api_key = os.environ.get("NVIDIA_API_KEY", "")
        self._url = "https://integrate.api.nvidia.com/v1/chat/completions"
        self.model = os.environ.get("NVIDIA_VISION_MODEL", "meta/llama-3.2-11b-vision-instruct")

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def url(self) -> str:
        return self._url

    def _get_payload(self, image_bytes: bytes) -> dict:
        b64 = self._encode_image(image_bytes)
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 4000,
            "response_format": {"type": "json_object"},
        }

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _parse_response(self, content: str) -> VisionResult | None:
        return _safe_parse(content)


# Factory to get the fallback chain
class TesseractVisionStrategy(VisionStrategy):
    """Ultimo recurso: OCR local via Tesseract (gratuito, sempre em CI).

    Só ativa quando todos os LLM providers falham. Retorna texto bruto com
    parser simples de precos.
    """

    provider_name = "tesseract_ocr"

    def __init__(self) -> None:
        super().__init__()
        self._available: bool | None = None  # lazy check

    @property
    def url(self) -> str:
        return ""

    @property
    def api_key(self) -> str:
        return ""

    def _get_payload(self, image_bytes: bytes) -> dict:
        return {}

    def _parse_response(self, content: str) -> VisionResult | None:
        return None

    def _get_headers(self) -> dict:
        return {}

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            self._available = True
        except Exception:
            logger.debug("[tesseract_ocr] binary not available, skipping")
            self._available = False
        return self._available

    def extract(self, image_bytes: bytes) -> VisionResult | None:
        if not self.is_available():
            return None
        try:
            import pytesseract
            from PIL import Image as PilImage
            import io
            img = PilImage.open(io.BytesIO(image_bytes))
            raw_text = pytesseract.image_to_string(img, lang="por")
            if not raw_text.strip():
                logger.debug("[tesseract_ocr] no text extracted")
                return None
            products = _ocr_text_to_products(raw_text)
            if not products:
                return None
            logger.info("[tesseract_ocr] extracted %d products via OCR", len(products))
            return VisionResult(products=products, raw_text=raw_text, provider="tesseract_ocr")
        except Exception as exc:
            logger.debug("[tesseract_ocr] OCR failed: %s", exc)
            return None


def _ocr_text_to_products(raw_text: str) -> list[dict]:
    """Tentativa simples de extrair produtos do texto bruto do OCR.

    Procura linhas com padrao <nome> + <preco> no mesmo paragrafo.
    """
    products: list[dict] = []
    lines = raw_text.splitlines()
    price_pattern = re.compile(r"R?\$?\s*(\d+[.,]\d{2})")
    current_name: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            current_name = []
            continue
        match = price_pattern.search(line)
        if match:
            name = " ".join(current_name + [line[:match.start()].strip()]) if current_name else line[:match.start()].strip()
            price_str = match.group(1).replace(",", ".")
            try:
                price = float(price_str)
                if price > 0 and name:
                    products.append({"product": name, "price": price, "unit": "", "validity_raw": "", "brand": "", "store": ""})
                    current_name = []
                    continue
            except ValueError:
                pass
        current_name.append(line)
    return products


class GitHubModelsVisionStrategy(VisionStrategy):
    """GitHub Models — GPT-4o com visao via Azure AI (gratuito, OpenAI-compat).

    Requer GITHUB_TOKEN no ambiente (ja existe no CI). Rate limit: ~10 RPM,
    50-150 RPD no free tier.
    """

    provider_name = "github_models"
    timeout = 15.0
    min_interval = 6.0  # ~10 RPM

    def __init__(self):
        super().__init__()
        self._api_key = os.environ.get("GH_MODELS_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
        self._url = "https://models.inference.ai.azure.com/chat/completions"
        self.model = "gpt-4o"

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def url(self) -> str:
        return self._url

    def _get_payload(self, image_bytes: bytes) -> dict:
        b64 = self._encode_image(image_bytes)
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 4000,
            "response_format": {"type": "json_object"},
        }

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _parse_response(self, content: str) -> VisionResult | None:
        return _safe_parse(content)


class GeminiVisionStrategy(VisionStrategy):
    """Google Gemini API — visao gratuita via Gemini 2.5 Flash.

    Requer GOOGLE_API_KEY no ambiente. Rate limit: ~10 RPM, ~100 RPD.
    Usa REST API direta (sem SDK) para evitar dependencia extra.
    """

    provider_name = "gemini"
    timeout = 15.0
    min_interval = 6.0  # ~10 RPM

    def __init__(self):
        super().__init__()
        self._api_key = os.environ.get("GOOGLE_API_KEY", "")
        base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self._url = f"{base_url}/gemini-2.5-flash:generateContent"

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def url(self) -> str:
        return self._url

    def _get_payload(self, image_bytes: bytes) -> dict:
        b64 = self._encode_image(image_bytes)
        return {
            "contents": [{
                "parts": [
                    {"text": _VISION_PROMPT},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                ]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4000,
            },
        }

    def _get_headers(self) -> dict:
        return {"Content-Type": "application/json"}

    def _get_request_params(self) -> dict:
        return {"key": self.api_key}

    def _parse_response(self, content: str) -> VisionResult | None:
        return _safe_parse(content)

    def _extract_content(self, data: dict) -> str:
        """Gemini response format: candidates[].content.parts[].text"""
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return ""

    def extract(self, image_bytes: bytes) -> VisionResult | None:
        if not self.is_available():
            logger.debug("[gemini_vision] Circuit breaker open, skipping")
            return None

        for attempt in range(VISION_MAX_RETRIES + 1):
            try:
                payload = self._get_payload(image_bytes)
                headers = self._get_headers()
                params = self._get_request_params()

                self._throttle()
                resp = get_client().post(self.url, headers=headers, json=payload, params=params, timeout=self.timeout)

                if resp.status_code == 429:
                    if VISION_FAIL_FAST_ON_429 and self._has_fallback:
                        self.open_circuit()
                        return None
                    if attempt < VISION_MAX_RETRIES:
                        wait = self._retry_after(resp, attempt)
                        logger.info("[gemini_vision] Rate limited, retry %d/%d em %.1fs", attempt + 1, VISION_MAX_RETRIES, wait)
                        time.sleep(wait)
                        continue
                    logger.info("[gemini_vision] Rate limited (retries exhausted)")
                    self.record_failure()
                    return None
                if resp.status_code >= 500:
                    logger.warning("[gemini_vision] Server error: %d", resp.status_code)
                    self.record_failure()
                    return None
                if resp.status_code >= 400:
                    logger.warning("[gemini_vision] Client error: %d — opening breaker", resp.status_code)
                    self.open_circuit()
                    return None
                resp.raise_for_status()

                data = resp.json()
                content = self._extract_content(data)
                result = self._parse_response(content)

                if result:
                    self.record_success()
                    result.provider = self.provider_name
                else:
                    logger.info("[gemini_vision] Invalid response format")
                    self.record_failure()

                return result

            except httpx.TimeoutException:
                logger.debug("[gemini_vision] Timeout (%.1fs)", self.timeout)
                self.record_failure()
                return None
            except Exception as e:
                logger.info("[gemini_vision] Error: %s", e)
                self.record_failure()
                return None
        return None


def get_vision_chain() -> list[VisionStrategy]:
    """Return a FRESH vision strategy chain in fallback order.

    Usado por quem quer instancias novas por chamada (testes). Para o fluxo de
    producao (varias imagens na mesma run), prefira ``_get_cached_chain()`` para
    que o circuit breaker persista entre imagens.
    """
    # Gemini (gratis, visao, rapido, ~0.5s fail se 429): melhor qualidade free.
    # NVIDIA (2.7s, llama-3.2-11b-vision): mais rapido dos working, qualidade boa.
    # GitHub Models (4.5s, GPT-4o): melhor qualidade absoluta, mas mais lento.
    # OpenRouter (0.1s fail se 429, gemma-4): fallback free.
    # Tesseract OCR local: ultimo recurso antes do extract_products().
    chain: list[VisionStrategy] = [
        GeminiVisionStrategy(),
        NvidiaVisionStrategy(),
        GitHubModelsVisionStrategy(),
        OpenRouterVisionStrategy(),
        TesseractVisionStrategy(),
    ]
    for i, s in enumerate(chain):
        s._has_fallback = i < len(chain) - 1
    return chain


# Instancia unica (module-level) — o circuit breaker persiste entre imagens de
# um mesmo scrape, entao um provider 429 uma vez nao eh re-tentado 60s por imagem.
_CACHED_CHAIN: list[VisionStrategy] | None = None


def _get_cached_chain() -> list[VisionStrategy]:
    global _CACHED_CHAIN
    if _CACHED_CHAIN is None:
        _CACHED_CHAIN = get_vision_chain()
    return _CACHED_CHAIN


def extract_products_via_vision(image_bytes: bytes) -> list[dict] | None:
    """Try each vision strategy in order until one succeeds.

    Usa a cadeia em cache (estado de circuit breaker compartilhado entre todas
    as imagens do scrape) para adaptar-se a limites de taxa: assim que um
    provider esgota o breaker, ele e pulado ate o cooldown, cedendo aos demais.
    """
    for strategy in _get_cached_chain():
        if not strategy.is_available():
            continue
        result = strategy.extract(image_bytes)
        if result and result.products:
            logger.info("[Vision] %s extracted %d products", strategy.provider_name, len(result.products))
            return result.products
    return None


def reset_vision_chain() -> None:
    """Forca recriacao da cadeia em cache (ex.: novo scrape, testes)."""
    global _CACHED_CHAIN
    _CACHED_CHAIN = None
