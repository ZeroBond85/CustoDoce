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


def test_get_ingredient_keywords_content_cache_not_id():
    """RPR: o cache de keywords não pode ser chaveado por id(lista).

    id() é reutilizável pelo Python após GC — duas listas distintas podem
    compartilhar o mesmo id e retornar keywords da coleta errada, descartando
    matches silenciosamente. O cache deve ser chaveado pelo CONTEÚDO.
    """
    ing_a = {"canonical_name": "Leite Condensado", "aliases": [], "search_terms": ["leite condensado"],
             "exclude_terms": [], "brands": []}
    ing_b = {"canonical_name": "Granulado Ao Leite", "aliases": [], "search_terms": ["granulado ao leite"],
             "exclude_terms": [], "brands": []}

    kws_a = collector._get_ingredient_keywords([ing_a])
    assert "CONDENSADO" in kws_a and "GRANULADO" not in kws_a

    # Lista diferente (mesmo tamanho) deve recalcular keywords
    kws_b = collector._get_ingredient_keywords([ing_b])
    assert "GRANULADO" in kws_b and "CONDENSADO" not in kws_b

    # Mesmo conteúdo retorna o cache (sem recalcular)
    kws_a2 = collector._get_ingredient_keywords([ing_a])
    assert kws_a2 == kws_a


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


def test_process_price_match_exclude_terms_nao_bloqueia_globalmente():
    """RPR #53: exclude_terms de UM ingrediente não pode descartar produto de OUTRO.

    Antes, o loop global em process_price_match descartava o produto se QUALQUER
    ingrediente tivesse exclude_terms batendo (ex: "baunilha" no exclude do Top
    Confete Morango bloqueava "Essência de Baunilha"). O matcher já aplica
    exclude_terms por candidato — o loop global era redundante e prejudicial.
    """
    store = MOCK_STORES[0]
    ingredients = [
        {
            "canonical_name": "Essência de Baunilha",
            "aliases": [],
            "search_terms": ["essencia baunilha", "baunilha"],
            "exclude_terms": [],
            "brands": [],
        },
        {
            "canonical_name": "Top Confete Morango",
            "aliases": [],
            "search_terms": ["top confete"],
            "exclude_terms": ["baunilha", "framboesa", "chocolate"],
            "brands": [],
        },
    ]
    with patch.object(collector, "upsert_price") as mock_up:
        entry = collector.process_price_match(
            store, "Essência de Baunilha Moça 395g", 10.5, "395g", ingredients
        )
    assert entry is not None
    assert entry["ingredient_id"] == "Essência de Baunilha"
    mock_up.assert_called_once()


def test_process_price_match_exclude_terms_bloqueia_candidato_errado():
    """exclude_terms deve impedir o candidato errado (Top Confete) de casar com
    produto de outro sabor (framboesa), resultando em None (sem match legítimo)."""
    store = MOCK_STORES[0]
    ingredients = [
        {
            "canonical_name": "Essência de Baunilha",
            "aliases": [],
            "search_terms": ["essencia baunilha", "baunilha"],
            "exclude_terms": [],
            "brands": [],
        },
        {
            "canonical_name": "Top Confete Morango",
            "aliases": [],
            "search_terms": ["top confete"],
            "exclude_terms": ["baunilha", "framboesa", "chocolate"],
            "brands": [],
        },
    ]
    with patch.object(collector, "upsert_price") as mock_up:
        entry = collector.process_price_match(
            store, "Confeite Top Framboesa 400g", 10.5, "400g", ingredients
        )
    # "Top Framboesa" é rejeitado pelo exclude do Top Confete e não casa com Essência
    assert entry is None
    mock_up.assert_not_called()


def test_process_price_match_batch_buffer_skips_single_upsert():
    """batch_entries presente → entry acumula no buffer e upsert_price NÃO é chamado.

    O caller (collector) faz flush via batch_upsert_prices depois do loop —
    elimina 1 HTTP round-trip por produto no scrape em massa.
    """
    store = MOCK_STORES[0]
    buffer = []
    with patch.object(collector, "upsert_price") as mock_up:
        entry = collector.process_price_match(
            store, "Leite Condensado Moça 395g", 10.5, "395g", MOCK_INGREDIENTS,
            batch_entries=buffer,
        )
    assert entry is not None
    assert len(buffer) == 1, "entry deveria acumular no buffer de batch"
    assert buffer[0]["ingredient_id"] == "Leite Condensado"
    mock_up.assert_not_called(), "batch path não deve chamar upsert_price unitário"


def test_process_price_match_batch_buffer_keeps_single_upsert_by_default():
    """Sem batch_entries (default None) → comportamento legacy: upsert_price unitário."""
    store = MOCK_STORES[0]
    with patch.object(collector, "upsert_price") as mock_up:
        entry = collector.process_price_match(
            store, "Leite Condensado Moça 395g", 10.5, "395g", MOCK_INGREDIENTS
        )
    assert entry is not None
    mock_up.assert_called_once()


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


def test_filter_by_env_stores_no_env_returns_all():
    stores = [{"name": "Tiendeo", "tier": 3}, {"name": "Carrefour Mercado", "tier": 2}]
    with patch.dict(os.environ, {}, clear=True):
        out = collector._filter_by_env_stores(stores)
    assert out == stores


def test_filter_by_env_stores_case_insensitive_substring():
    stores = [
        {"name": "Tiendeo", "tier": 3},
        {"name": "Carrefour Mercado", "tier": 2},
        {"name": "Kimbino", "tier": 3},
    ]
    with patch.dict(os.environ, {"CUSTODOCE_STORES_FILTER": "tiendeo, CARREFOUR"}):
        out = collector._filter_by_env_stores(stores)
    assert [s["name"] for s in out] == ["Tiendeo", "Carrefour Mercado"]


def test_filter_by_env_stores_empty_and_blank_terms():
    stores = [{"name": "Tiendeo"}, {"name": "Kimbino"}]
    with patch.dict(os.environ, {"CUSTODOCE_STORES_FILTER": "  ,  "}):
        assert collector._filter_by_env_stores(stores) == stores
    with patch.dict(os.environ, {"CUSTODOCE_STORES_FILTER": "   "}):
        assert collector._filter_by_env_stores(stores) == stores


def test_filter_by_env_stores_no_match_returns_empty():
    stores = [{"name": "Tiendeo"}, {"name": "Kimbino"}]
    with patch.dict(os.environ, {"CUSTODOCE_STORES_FILTER": "Loja Inexistente"}):
        assert collector._filter_by_env_stores(stores) == []


def test_filter_by_env_stores_exclusion_prefix():
    stores = [
        {"name": "Tiendeo", "tier": 3},
        {"name": "Carrefour Mercado", "tier": 2},
        {"name": "Kimbino", "tier": 3},
        {"name": "Spani Atacadista", "tier": 1},
    ]
    with patch.dict(os.environ, {"CUSTODOCE_STORES_FILTER": "-tiendeo,-carrefour"}):
        out = collector._filter_by_env_stores(stores)
    assert [s["name"] for s in out] == ["Kimbino", "Spani Atacadista"]


def test_filter_by_env_stores_exclusion_only_blanks_returns_all():
    stores = [{"name": "Tiendeo"}, {"name": "Kimbino"}]
    with patch.dict(os.environ, {"CUSTODOCE_STORES_FILTER": "-,-"}):
        assert collector._filter_by_env_stores(stores) == stores


def test_filter_by_env_stores_mixed_inclusion_then_exclusion():
    stores = [{"name": "Tiendeo"}, {"name": "Kimbino"}]
    with patch.dict(os.environ, {"CUSTODOCE_STORES_FILTER": "tiendeo,-kimbino"}):
        assert [s["name"] for s in collector._filter_by_env_stores(stores)] == ["Tiendeo"]
    # Exclusão remove mesmo loja que casaria com inclusão.
    with patch.dict(os.environ, {"CUSTODOCE_STORES_FILTER": "tiendeo,-tiendeo"}):
        assert collector._filter_by_env_stores(stores) == []


def test_is_pdf_flyer_published_normal_days():
    with patch.dict(os.environ, {}, clear=True):
        assert collector._is_pdf_flyer_published({"publish_day": "wednesday"}, "wednesday") is True
        assert collector._is_pdf_flyer_published({"publish_day": "wednesday"}, "monday") is False
        # Thursday é sempre coberto (fallback de coleta).
        assert collector._is_pdf_flyer_published({"publish_day": "sunday"}, "thursday") is True
        # publish_day ausente → default wednesday.
        assert collector._is_pdf_flyer_published({}, "wednesday") is True
        assert collector._is_pdf_flyer_published({}, "saturday") is False
        # publish_day como lista.
        assert collector._is_pdf_flyer_published({"publish_day": ["tuesday", "friday"]}, "friday") is True
        assert collector._is_pdf_flyer_published({"publish_day": ["tuesday", "friday"]}, "monday") is False


def test_is_pdf_flyer_published_force_overrides():
    """Regressão P0: --force (CUSTODOCE_FORCE_SCRAPE=1) deve coletar PDFs
    mesmo fora do publish_day (Assaí/Atacadão/Mercadão pulados em dias não
    programados)."""
    store = {"publish_day": "wednesday"}
    with patch.dict(os.environ, {"CUSTODOCE_FORCE_SCRAPE": "1"}):
        assert collector._is_pdf_flyer_published(store, "saturday") is True
        assert collector._is_pdf_flyer_published(store, "monday") is True


def test_collect_tier1_pdfs_force_includes_all_pdf_stores():
    """--force deve incluir TODOS os pdf_flyer stores, mesmo fora do publish_day."""
    stores = [
        {"name": "Assaí Atacadista", "tier": 1, "type": "pdf_flyer", "publish_day": "wednesday"},
        {"name": "Atacadão", "tier": 1, "type": "pdf_flyer", "publish_day": "thursday"},
        {"name": "Mercadão Atacadista", "tier": 1, "type": "pdf_flyer", "publish_day": "friday"},
    ]
    with patch.dict(os.environ, {"CUSTODOCE_FORCE_SCRAPE": "1"}), \
         patch.object(collector, "load_stores", return_value=stores), \
         patch.object(collector, "_collect_prices", return_value=[]) as mock_coll:
        collector.collect_tier1_pdfs([])
    called_stores = mock_coll.call_args[0][0]
    assert [s["name"] for s in called_stores] == ["Assaí Atacadista", "Atacadão", "Mercadão Atacadista"]


def test_collect_tier1_pdfs_normal_day_filters():
    """Sem force, só lojas com publish_day hoje (ou quinta) entram."""
    stores = [
        {"name": "Assaí Atacadista", "tier": 1, "type": "pdf_flyer", "publish_day": "wednesday"},
        {"name": "Atacadão", "tier": 1, "type": "pdf_flyer", "publish_day": "thursday"},
        {"name": "Mercadão Atacadista", "tier": 1, "type": "pdf_flyer", "publish_day": "friday"},
    ]
    fake_date = type("FakeDate", (), {"today": staticmethod(lambda: __import__("datetime").date(2026, 8, 5))})
    with patch.dict(os.environ, {}, clear=True), \
         patch.object(collector, "load_stores", return_value=stores), \
         patch.object(collector, "date", fake_date), \
         patch.object(collector, "_collect_prices", return_value=[]) as mock_coll:
        collector.collect_tier1_pdfs([])
    called_stores = mock_coll.call_args[0][0]
    assert [s["name"] for s in called_stores] == ["Assaí Atacadista"]


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


class _FakeMatcher:
    """Fake semantic matcher que retorna valores controlados por teste."""

    def __init__(self, semantic_value: float = 0.0):
        self._semantic = semantic_value

    def get_similarity(self, product_text: str, ingredient: dict) -> float:
        return self._semantic

    def combined_score(self, rf_score: float, semantic_score: float) -> float:
        return 0.6 * (rf_score / 100.0) + 0.4 * semantic_score


def _gray_zone_ingredients() -> list[dict]:
    """Ingredientes com candidato de chocolate (RF ~71 no gray-zone 60-79)."""
    return [
        {
            "canonical_name": "Chocolate Meio Amargo em Barra",
            "aliases": [],
            "search_terms": ["chocolate meio amargo", "barra meio amargo"],
            "exclude_terms": ["gotas"],
            "brands": [],
        },
        {
            "canonical_name": "Gotas de Chocolate Meio Amargo",
            "aliases": [],
            "search_terms": ["gotas chocolate meio amargo", "gotas meio amargo"],
            "exclude_terms": [],
            "brands": [],
        },
    ]


def _fake_feature_true(key: str, **kw):
    """get_feature mock: retorna True para features.ai.enabled e o default para demais."""
    if key == "features.ai.enabled":
        return True
    return kw.get("default", True)


def _fake_matcher(semantic_value: float) -> _FakeMatcher:
    return _FakeMatcher(semantic_value=semantic_value)


def test_process_price_match_gray_zone_semantic_persists():
    """T1.1 RPR: RF 60-79 + semantic alto (combined >= 0.80) deve PERSISTIR.

    Antes do fix, match_ingredient usava threshold=80 e retornava None para
    gray-zone → o semantic (linha ~245 'if ingredient and score >= 60') nunca
    rodava e o item caía na review_queue com confidence = RF puro.
    """
    store = MOCK_STORES[0]
    captured = []
    with patch.object(collector, "get_matcher", return_value=_fake_matcher(0.95)), \
         patch("services.config.get_feature", side_effect=_fake_feature_true), \
         patch.object(collector, "upsert_price", side_effect=captured.append):
        entry = collector.process_price_match(
            store, "Gotas de Chocolate Meio Amargo 1kg", 25.9, "1kg", _gray_zone_ingredients()
        )
    assert entry is not None, "combined >= 0.80 deve persistir via upsert_price"
    assert captured, "upsert_price deveria ser chamado"
    assert captured[0]["ingredient_id"] == "Gotas de Chocolate Meio Amargo"


def test_process_price_match_gray_zone_fp_discarded_below_threshold():
    """Gray-zone RF 60-79 + semantic 0 (combined < 0.80) é descartado.

    Sprint 18 alinhou review_threshold ao gate de persistência (0.80): itens
    70-79% nunca persistiriam e inflavam a fila (~646/dia). Política atual:
    combined < 0.80 → sem upsert E sem review (descarte silencioso).
    """
    store = MOCK_STORES[0]
    with patch.object(collector, "get_matcher", return_value=_fake_matcher(0.0)), \
         patch("services.config.get_feature", side_effect=_fake_feature_true), \
         patch.object(collector, "upsert_price") as mock_up, \
         patch.object(collector, "insert_review_item") as mock_rev, \
         patch.object(collector, "rank_ingredients",
                      return_value=[(_gray_zone_ingredients()[0], 79.3, "proximo_nome", "chocolate meio amargo")]):
        entry = collector.process_price_match(
            store, "Chocolate Seleção Amargo 52% Cacau - 1,01 kg", 42.9, "1.01kg", _gray_zone_ingredients()
        )
    assert entry is None, "combined < 0.80 não deve persistir"
    mock_up.assert_not_called()
    mock_rev.assert_not_called(), "combined < 0.80 não vai mais para review_queue (Sprint 18+)"


def test_process_price_match_gray_zone_semantic_zero_still_works():
    """T1.1: semantic=0 deve preservar o comportamento legado (combined = RF/100)."""
    store = MOCK_STORES[0]
    with patch.object(collector, "get_matcher", return_value=_fake_matcher(0.0)), \
         patch("services.config.get_feature", side_effect=_fake_feature_true), \
         patch.object(collector, "upsert_price") as mock_up, \
         patch.object(collector, "insert_review_item") as mock_rev, \
         patch.object(collector, "rank_ingredients",
                      return_value=[(_gray_zone_ingredients()[0], 79.3, "proximo_nome", "chocolate meio amargo")]):
        collector.process_price_match(
            store, "Chocolate Seleção Amargo 52% Cacau - 1,01 kg", 42.9, "1.01kg", _gray_zone_ingredients()
        )
    mock_up.assert_not_called()
    mock_rev.assert_not_called(), "combined 0.793 < 0.80: descartado (política Sprint 18+)"


def test_process_price_match_high_rf_unaffected():
    """T1.1: RF >= 80 deve persistir direto (threshold=60 não muda o candidato)."""
    store = MOCK_STORES[0]
    captured = []
    ing = {"canonical_name": "Leite Condensado", "aliases": [], "search_terms": ["leite condensado"],
           "exclude_terms": [], "brands": []}
    with patch.object(collector, "get_matcher", return_value=_FakeMatcher(semantic_value=0.0)), \
         patch("services.config.get_feature", side_effect=lambda key, **kw: True), \
         patch.object(collector, "upsert_price", side_effect=captured.append):
        entry = collector.process_price_match(
            store, "Leite Condensado Moça 395g", 10.5, "395g", [ing]
        )
    assert entry is not None
    assert captured, "RF >= 80 continua persistindo direto"
    assert captured[0]["ingredient_id"] == "Leite Condensado"
