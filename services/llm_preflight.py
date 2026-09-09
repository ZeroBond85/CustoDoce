"""LLM preflight probe — verifica provedores antes do scrape.

Uma única chamada "ping" por provider (Groq, OpenRouter) no boot do scrape.
Se falhar com 400/404 -> marca provedor como deprecated.
Se 429/5xx -> marca cooldown temporário.
Resultado gravado em os.environ["LLM_PREFLIGHT"] (JSON) para reuso na sessão.
"""

import os
import json
import time
import httpx
from typing import Any, TypedDict
from collections.abc import Callable


class _ProviderEndpoint(TypedDict):
    url: str
    headers: Callable[[str], dict[str, str]]


_PROVIDER_ENDPOINTS: dict[str, _ProviderEndpoint] = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/models",
        "headers": lambda key: {"Authorization": f"Bearer {key}"},
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/models",
        "headers": lambda key: {"Authorization": f"Bearer {key}"},
    },
}

_ENV_KEY = "LLM_PREFLIGHT"
_CACHE_TTL = 180  # segundos (3 min) — reusa em re-runs curtos


def _load_cache() -> dict[str, Any]:
    raw = os.environ.get(_ENV_KEY)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {}


def _save_cache(cache: dict[str, Any]) -> None:
    os.environ[_ENV_KEY] = json.dumps(cache, ensure_ascii=False)


def _provider_key(provider: str) -> str:
    return f"llm_preflight_{provider}"


def _get_cached(provider: str) -> dict[str, Any] | None:
    cache = _load_cache()
    key = _provider_key(provider)
    entry = cache.get(key)
    if isinstance(entry, dict) and time.time() - entry.get("ts", 0) < _CACHE_TTL:
        return entry
    return None


def _set_cache(provider: str, result: dict[str, Any]) -> None:
    cache = _load_cache()
    cache[_provider_key(provider)] = result
    _save_cache(cache)


def _probe_provider(provider: str, timeout: float = 5.0) -> dict[str, Any]:
    """Faz 1 chamada GET /models ao provider. Retorna dict com ok/version/error."""
    api_key = os.environ.get(f"{provider.upper()}_API_KEY")
    if not api_key:
        return {"ok": False, "error": "no_api_key", "version": None}

    endpoint = _PROVIDER_ENDPOINTS.get(provider)
    if not endpoint:
        return {"ok": False, "error": "unknown_provider", "version": None}

    headers_fn = endpoint["headers"]
    url = endpoint["url"]
    headers = headers_fn(api_key)

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                # Tenta extrair modelo default da lista
                data = resp.json()
                model = None
                if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                    for m in data["data"]:
                        if isinstance(m, dict) and m.get("id"):
                            model = m["id"]
                            break
                return {"ok": True, "version": model, "error": None}
            elif resp.status_code == 404:
                # Modelo removido / endpoint não encontrado
                return {"ok": False, "error": "not_found", "version": None}
            elif resp.status_code == 400:
                # Modelo removido / parâmetros inválidos
                return {"ok": False, "error": "bad_request", "version": None}
            elif resp.status_code in (429, 502, 503, 504):
                return {"ok": False, "error": f"cooldown_{resp.status_code}", "version": None}
            else:
                return {"ok": False, "error": f"http_{resp.status_code}", "version": None}
    except httpx.TimeoutException:
        return {"ok": False, "error": "timeout", "version": None}
    except httpx.RequestError as e:
        return {"ok": False, "error": f"request_error_{type(e).__name__}", "version": None}


def llm_preflight(providers: list[str] | None = None, force: bool = False) -> dict[str, bool]:
    """Roda preflight para provedores indicados. Retorna {provider: ok}."""
    providers = providers if providers is not None else ["groq", "openrouter"]
    results: dict[str, bool] = {}

    for provider in providers:
        # Pula provedores deprecated
        if _is_deprecated(provider):
            results[provider] = False
            continue

        # Cache check
        if not force:
            cached = _get_cached(provider)
            if cached is not None:
                # Se tem entrada no cache (mesmo ok=False), usa o valor do cache
                results[provider] = cached.get("ok", False)
                continue

        # Probe real
        result = _probe_provider(provider)
        result["ts"] = time.time()
        _set_cache(provider, result)
        results[provider] = result.get("ok", False)

    return results


def _is_deprecated(provider: str) -> bool:
    """Verifica se provedor está marcado como deprecated."""
    cache = _load_cache()
    if "__deprecated__" in cache:
        return provider in cache["__deprecated__"]
    return False


def get_best_provider(providers: list[str] | None = None) -> str | None:
    """Retorna o primeiro provider saudável na ordem dada, ou None."""
    providers = providers if providers is not None else ["groq", "openrouter"]
    for p in providers:
        # Pula provedores deprecated
        if _is_deprecated(p):
            continue
        cached = _get_cached(p)
        if cached and cached.get("ok"):
            return p
    # Se cache vazio, roda preflight rápido
    results = llm_preflight(providers, force=True)
    for p in providers:
        if _is_deprecated(p):
            continue
        if results.get(p):
            return p
    return None


def mark_deprecated(provider: str) -> None:
    """Marca manualmente um provedor como deprecated (ex.: ao receber 400/404 downstream)."""
    cache = _load_cache()
    key = _provider_key(provider)
    if key in cache:
        cache[key] = {"ok": False, "error": "deprecated", "version": "REMOVIDO", "ts": time.time()}
        _save_cache(cache)
    # Adiciona ao set de deprecated
    if "__deprecated__" not in cache:
        cache["__deprecated__"] = []
    if provider not in cache["__deprecated__"]:
        cache["__deprecated__"].append(provider)
        _save_cache(cache)
    # Invalida também a cache de _get_cached
    from services.llm_preflight import _load_cache as _lc
    cache2 = _lc()
    key2 = _provider_key(provider)
    if key2 in cache2:
        del cache2[key2]
