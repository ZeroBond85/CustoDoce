"""
Testes para as novas funcionalidades da Fase 20:
- SemanticMatcher (parsers/semantic_matcher.py)
- PriceIntelligence (services/price_intelligence.py)
- LLMClassifier (parsers/llm_classifier.py)
- Auto-Learning Aliases (services/price_service.py)
- Cleanup functions (services/price_service.py)
- process_price_match AI integration (main.py)
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
os.environ.setdefault("GROQ_API_KEY", "test-key")


# ─────────────────────────────────────────────────────────────────
# Testes para SemanticMatcher (parsers/semantic_matcher.py)
# ─────────────────────────────────────────────────────────────────

class TestSemanticMatcher:
    """Testes para SemanticMatcher - embeddings locais com sentence-transformers."""

    def test_semantic_matcher_exact_match(self):
        from parsers.semantic_matcher import get_matcher
        sm = get_matcher()
        ing = {"canonical_name": "Leite Condensado Integral", "aliases": ["Moça", "Piracanjuba"]}
        sim = sm.get_similarity("Leite Condensado Moça 395g", ing)
        assert sim >= 0.50, f"Expected similarity >= 0.50, got {sim}"

    def test_semantic_matcher_no_match(self):
        from parsers.semantic_matcher import get_matcher
        sm = get_matcher()
        ing = {"canonical_name": "Leite Condensado Integral", "aliases": ["Moça"]}
        sim = sm.get_similarity("Arroz Branco 5kg", ing)
        assert sim < 0.5, f"Expected low similarity for unrelated product, got {sim}"

    def test_combined_score_formula(self):
        from parsers.semantic_matcher import get_matcher
        sm = get_matcher()
        rf_score = 75.0
        semantic_score = 0.90
        combined = sm.combined_score(rf_score, semantic_score)
        expected = 0.6 * (75.0 / 100.0) + 0.4 * 0.90
        assert abs(combined - expected) < 0.001, f"Expected {expected}, got {combined}"

    def test_cache_hit(self):
        from parsers.semantic_matcher import get_matcher
        sm = get_matcher()
        ing = {"canonical_name": "Test Ingrediente", "aliases": ["Teste"]}
        sim1 = sm.get_similarity("Test Ingrediente X", {"canonical_name": "Test Ingrediente", "aliases": ["Teste"]})
        sim2 = sm.get_similarity("Test Ingrediente X", {"canonical_name": "Test Ingrediente", "aliases": ["Teste"]})
        assert abs(sim1 - sim2) < 0.001, "Cache should return same result"


# ─────────────────────────────────────────────────────────────────
# Testes para PriceIntelligence (services/price_intelligence.py)
# ─────────────────────────────────────────────────────────────────

class TestPriceIntelligence:
    """Testes para PriceIntelligence - detecção de anomalias via Z-score + Isolation Forest."""

    def setup_method(self):
        # Mock get_price_history to return sufficient historical data
        # Values: 9.0, 9.5, 10.0, 10.5, 11.0 -> mean=10.0, std~0.7
        # For OFERTA_REAL test: 9.2 gives z = (9.2-10)/0.7 = -1.43 -> OFERTA_REAL
        self.mock_prices = [
            {"normalized": {"price_per_kg": 9.0}, "store_id": "store1", "ingredient_id": "ing1", "collected_at": "2026-01-01"},
            {"normalized": {"price_per_kg": 9.5}, "store_id": "store1", "ingredient_id": "ing1", "collected_at": "2026-01-02"},
            {"normalized": {"price_per_kg": 10.0}, "store_id": "store1", "ingredient_id": "ing1", "collected_at": "2026-01-03"},
            {"normalized": {"price_per_kg": 10.5}, "store_id": "store1", "ingredient_id": "ing1", "collected_at": "2026-01-04"},
            {"normalized": {"price_per_kg": 11.0}, "store_id": "store1", "ingredient_id": "ing1", "collected_at": "2026-01-05"},
        ]

    def test_normal_price_no_anomaly(self):
        from services.price_intelligence import PriceIntelligence

        with patch("services.price_intelligence.get_price_history", return_value=self.mock_prices):
            pi = PriceIntelligence()
            anomaly = pi.detect_anomaly("ing1", "store1", 10.2)
            assert not anomaly["is_anomaly"]
            assert anomaly["tag"] == "NORMAL"

    def test_anomaly_low_price(self):
        from services.price_intelligence import PriceIntelligence

        with patch("services.price_intelligence.get_price_history", return_value=self.mock_prices):
            pi = PriceIntelligence()
            anomaly = pi.detect_anomaly("ing1", "store1", 8.5)
            assert anomaly["is_anomaly"]
            assert anomaly["tag"] == "PRECO_SUSPEITO"
            assert anomaly["severity"] == "medium"

    def test_anomaly_high_price(self):
        from services.price_intelligence import PriceIntelligence

        with patch("services.price_intelligence.get_price_history", return_value=self.mock_prices):
            pi = PriceIntelligence()
            anomaly = pi.detect_anomaly("ing1", "store1", 13.5)
            assert anomaly["is_anomaly"]
            assert anomaly["tag"] == "PRECO_ELEVADO"
            assert anomaly["severity"] == "high"

    def test_oferta_real(self):
        from services.price_intelligence import PriceIntelligence

        with patch("services.price_intelligence.get_price_history", return_value=self.mock_prices):
            pi = PriceIntelligence()
            # 9.2 with mean=10.0, std~0.5 -> zscore = -1.6 -> OFERTA_REAL
            anomaly = pi.detect_anomaly("ing1", "store1", 9.2)
            assert not anomaly["is_anomaly"]
            assert anomaly["tag"] == "OFERTA_REAL"

    def test_insufficient_history(self):
        from services.price_intelligence import PriceIntelligence

        few_prices = [
            {"normalized": {"price_per_kg": 10.0}, "store_id": "store1", "ingredient_id": "ing1"},
            {"normalized": {"price_per_kg": 10.2}, "store_id": "store1", "ingredient_id": "ing1"},
        ]
        with patch("services.price_intelligence.get_price_history", return_value=few_prices):
            pi = PriceIntelligence()
            anomaly = pi.detect_anomaly("ing1", "store1", 10.0)
            assert not anomaly["is_anomaly"]
            assert anomaly["tag"] == "SEM_HISTORICO"

    def test_enrich_prices(self):
        from services.price_intelligence import PriceIntelligence

        with patch("services.price_intelligence.get_price_history", return_value=self.mock_prices):
            pi = PriceIntelligence()
            prices = [
                {"ingredient_id": "ing1", "store_id": "store1", "normalized": {"price_per_kg": 10.0}},
                {"ingredient_id": "ing1", "store_id": "store2", "normalized": {"price_per_kg": 8.0}},
            ]
            pi = PriceIntelligence()
            enriched = pi.enrich_prices(prices)
            assert len(enriched) == 2
            assert "ai_tags" in enriched[0]
            assert "ai_anomaly" in enriched[0]


# ─────────────────────────────────────────────────────────────────
# Testes para LLMClassifier (parsers/llm_classifier.py)
# ─────────────────────────────────────────────────────────────────

class TestLLMClassifier:
    """Testes para LLMClassifier via Groq API (mockado)."""

    def test_no_api_key_returns_none(self):
        from parsers.llm_classifier import LLMClassifier
        import os
        old_key = os.environ.pop("GROQ_API_KEY", None)
        try:
            classifier = LLMClassifier()
            result = classifier.classify_sync("Leite Condensado Moça 395g", [{"canonical_name": "Leite Condensado", "aliases": []}])
            assert result is None
        finally:
            if old_key:
                os.environ["GROQ_API_KEY"] = old_key


class TestCleanupFunctions:
    """Testes para as novas funções de cleanup."""

    def test_cleanup_old_flyers_all(self):
        from services.price_service import cleanup_old_flyers_all
        result = cleanup_old_flyers_all(180)
        assert "deleted" in result

    def test_cleanup_resolved_review_items(self):
        from services.price_service import cleanup_resolved_review_items
        result = cleanup_resolved_review_items(30)
        assert "deleted" in result


# ─────────────────────────────────────────────────────────────────
# Testes para process_price_match com IA (main.py)
# ─────────────────────────────────────────────────────────────────

class TestProcessPriceMatchAI:
    """Testes de integração do process_price_match com IA."""

    def test_exact_match_auto_approve(self):
        """Score >= 80% -> auto-aprova sem semantic/LLM."""
        from main import process_price_match

        with patch("main.match_ingredient") as mock_match:
            with patch("main.upsert_price") as mock_upsert:
                mock_match.return_value = ({"canonical_name": "Leite Condensado", "aliases": [], "search_terms": []}, 95.0, "exato")
                store = {"name": "Test", "type": "pdf", "tier": 1}
                ing_list = [{"canonical_name": "Leite Condensado", "aliases": [], "search_terms": []}]
                result = process_price_match(store, "Leite Condensado Moça 395g", 39.90, "cx 12x395g", ing_list)
                assert result is not None
                mock_upsert.assert_called_once()

    def test_exact_fuzzy_match_auto_approve(self):
        """Score >= 80% (exact/fuzzy) -> auto-aprova sem semantic."""
        from main import process_price_match

        with patch("main.match_ingredient") as mock_match, patch("main.upsert_price") as mock_upsert:
            mock_match.return_value = ({"canonical_name": "Farinha", "aliases": [], "search_terms": []}, 95.0, "exato")
            store = {"name": "Test", "type": "pdf", "tier": 1}
            ing_list = [{"canonical_name": "Farinha", "aliases": [], "search_terms": []}]
            result = process_price_match(store, "Farinha de Trigo 1kg", 5.90, "1kg", ing_list)
            assert result is not None
            mock_upsert.assert_called_once()

    def test_review_queue_fallback(self):
        """Score 55-65% -> review queue (combined >= 0.55 and < 0.65)."""
        from main import process_price_match

        with patch("main.match_ingredient") as mock_match, patch("main.rank_ingredients", return_value=[]):
            with patch("main.insert_review_item") as mock_insert:
                with patch("main.has_ingredient_keyword", return_value=True):
                    # Score 60% -> combined = 0.60 -> review queue (0.55 <= 0.60 < 0.65)
                    mock_match.return_value = (None, 60.0, "none")
                    store = {"name": "Test", "type": "pdf", "tier": 1}
                    ing_list = [{"canonical_name": "Leite Condensado", "aliases": [], "search_terms": []}]
                    result = process_price_match(store, "Produto Desconhecido XYZ", 10.0, "un", ing_list)
                    assert result is None
                    mock_insert.assert_called_once()


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
