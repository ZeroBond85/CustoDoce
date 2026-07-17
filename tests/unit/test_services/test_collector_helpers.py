"""Unit tests for services/collector.py helpers (pure + DB-mockable)."""

from __future__ import annotations

import os
from unittest.mock import patch

from services import collector
from tests.unit.fixtures.mock_data import MOCK_INGREDIENTS, MOCK_STORES


def test_get_default_frequency_minutes_by_tier():
    assert collector._get_default_frequency_minutes({"tier": 1}) == 10080
    assert collector._get_default_frequency_minutes({"tier": 2}) == 1440
    assert collector._get_default_frequency_minutes({"tier": 3}) == 1440
    assert collector._get_default_frequency_minutes({"tier": 4}) == 43200
    assert collector._get_default_frequency_minutes({}) == 1440


def test_extract_validity_from_product():
    assert collector._extract_validity_from_product("Promo valido ate 15/07/2026") != ""
    assert collector._extract_validity_from_product("sem validade") == ""


def test_get_ingredient_keywords_non_empty():
    kws = collector._get_ingredient_keywords(MOCK_INGREDIENTS)
    assert isinstance(kws, set)
    assert len(kws) > 0


def test_build_product_entry_normalizes():
    store = MOCK_STORES[0]
    ing = MOCK_INGREDIENTS[0]
    entry = collector.build_product_entry(store, ing, "Leite Condensado Moça 395g", 10.5, "395g", 0.9)
    assert entry["ingredient_id"] == "Leite Condensado"
    assert entry["store_name"] == store["name"]
    assert entry["normalized"] is not None
    assert abs(entry["normalized"]["price_per_kg"] - 10.5 / 0.395) < 0.05
    assert entry["brand"] == "Moça"


def test_process_price_match_returns_entry():
    store = MOCK_STORES[0]
    captured = []
    with patch.object(collector, "upsert_price", side_effect=captured.append):
        entry = collector.process_price_match(
            store, "Leite Condensado Moça 395g", 10.5, "395g", MOCK_INGREDIENTS
        )
    assert entry is not None
    assert captured, "upsert_price deveria ser chamado no match"
    assert captured[0]["ingredient_id"] == "Leite Condensado"


def test_process_price_match_no_keyword_returns_none():
    store = MOCK_STORES[0]
    with patch.object(collector, "upsert_price") as mock_up:
        entry = collector.process_price_match(
            store, "Produto Totalmente Aleatorio Xyz", 9.9, "1kg", MOCK_INGREDIENTS
        )
    assert entry is None
    mock_up.assert_not_called()


def test_should_skip_store_bypassed_by_force_env():
    """Regressão: CUSTODOCE_FORCE_SCRAPE=1 força coleta full sem tocar no DB.

    Assim, para um scrape full não é preciso zerar scrape_frequencies (que
    quebra a integração — testes exigem >=20 enabled). --force é o caminho seguro.
    """
    store = MOCK_STORES[0]
    with patch.dict(os.environ, {"CUSTODOCE_FORCE_SCRAPE": "1"}):
        with patch.object(collector, "get_supabase") as mock_db:
            skip, reason = collector._should_skip_store(store)
    assert skip is False
    assert reason == ""
    mock_db.assert_not_called()


def test_collect_tier1_api_flyers_routes_products_as_prices():
    """Regressão scrape 29582782313: produtos extraídos por vision (name+price,
    SEM image_url) das lojas api_flyer (Max/Roldão) eram roteados pelo pipeline de
    flyer-IMAGE e descartados silenciosamente (0 coletados apesar de 120 extraídos).

    Agora collect_tier1_api_flyers usa o pipeline de PREÇOS: os produtos passam por
    process_price_match e viram preços — nenhum é descartado por falta de image_url.
    """
    class _FakeApiScraper:
        def __init__(self, store):
            self.store = store

    api_store = {
        "name": "Roldão Atacadista",
        "tier": 1,
        "type": "api_flyer",
        "scraper": "roldao_api_scraper",
        "vision_timeout_seconds": 300,
    }
    # Produtos extraídos por vision: têm product/price, NÃO têm image_url.
    vision_products = [
        {"product": "Leite Condensado Moça 395g", "price": 4.99, "unit": "395g"},
        {"product": "Creme de Leite Nestlé 200g", "price": 3.49, "unit": "200g"},
    ]
    matched: list[dict] = []
    with patch.object(collector, "load_stores", return_value=[api_store]), \
         patch.dict(collector.API_SCRAPER_MAP, {"roldao_api_scraper": _FakeApiScraper}), \
         patch.object(collector, "_should_skip_store", return_value=(False, "")), \
         patch.object(collector, "_run_scraper_isolated", return_value=(vision_products, None)), \
         patch.object(collector, "process_price_match",
                      side_effect=lambda *a, **k: matched.append(a) or {"ingredient_id": "x", "raw_price": a[2]}):
        result = collector.collect_tier1_api_flyers(MOCK_INGREDIENTS)

    assert len(matched) == 2, "todos os produtos extraídos devem passar por process_price_match"
    assert len(result) == 2, "produtos sem image_url NÃO devem ser descartados — viram preços"
