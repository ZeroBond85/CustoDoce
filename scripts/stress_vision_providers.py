"""Stress test local de todos os providers de vision (flyer real do Max).

Carrega .env (API keys), baixa 1 encarte real via MaxApiScraper,
e manda a imagem para CADA strategy de vision com timeout agressivo,
reportando: latência, status HTTP, e se devolveu JSON válido com produtos.

Uso:
    python scripts/stress_vision_providers.py
"""
from __future__ import annotations

import io
import sys
import time

import dotenv
from PIL import Image

from parsers.vision_strategies import (
    GroqVisionStrategy,
    NvidiaVisionStrategy,
    OpenRouterVisionStrategy,
    _downscale_image,
)
from services.config_db import get_store_by_name

dotenv.load_dotenv(".env")


def _get_one_flyer_image() -> bytes:
    """Baixa 1 imagem de encarte REAL do Max (via API) e devolve JPEG em bytes."""
    from scrapers.max_api_scraper import MaxApiScraper
    from services.http_client import get_client

    store = get_store_by_name("Max Atacadista SP")
    with MaxApiScraper(store) as scraper:
        offers = scraper.get_offers()
        if not offers:
            raise SystemExit("Nenhum encarte do Max disponível")
        # pega a 1a imagem crua via parse_offer
        entries = scraper.parse_offer(offers[0])
        if not entries:
            raise SystemExit("parse_offer vazio")
        url = entries[0]["image_url"]
        print(f"[stress] {len(entries)} imagens; baixando: {url[:80]}...")
        data = get_client().get(url, timeout=60).content
        if not data:
            raise SystemExit("Falha ao baixar imagem do encarte")
    img = _downscale_image(data)
    print(f"[stress] imagem obtida: {len(img)} bytes")
    return img


def _score(result) -> str:
    if result is None:
        return "NENHUM resultado (None)"
    prods = result.products if hasattr(result, "products") else []
    return f"{len(prods)} produtos | raw_text={len(result.raw_text or '')} chars"


def main() -> int:
    image = _get_one_flyer_image()
    # garante JPEG decodificável
    with Image.open(io.BytesIO(image)) as im:
        im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        image = buf.getvalue()

    strategies = [
        GroqVisionStrategy(),
        OpenRouterVisionStrategy(),
        NvidiaVisionStrategy(),
    ]

    print("\n=== STRESS: 1 imagem de flyer real, cada provider ===\n")
    results = []
    for strat in strategies:
        name = strat.provider_name
        if not strat.api_key:
            print(f"  [{name}] PULADO (sem API key)")
            results.append((name, "sem key", None, None))
            continue
        t0 = time.time()
        try:
            # força timeout curto p/ stressar latência
            strat.DEFAULT_TIMEOUT = 25.0  # type: ignore[attr-defined]
            res = strat.extract(image)
            elapsed = time.time() - t0
            score = _score(res)
            print(f"  [{name}] OK em {elapsed:.1f}s -> {score}")
            results.append((name, f"{elapsed:.1f}s", "ok", score))
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  [{name}] ERRO em {elapsed:.1f}s: {type(e).__name__}: {str(e)[:80]}")
            results.append((name, f"{elapsed:.1f}s", "erro", str(e)[:80]))

    print("\n=== RESUMO ===")
    for name, tempo, status, detalhe in results:
        print(f"  {name:12s} | {tempo:10s} | {status:5s} | {detalhe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
