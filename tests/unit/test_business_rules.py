"""Regressão de falso-positivo de negócio (motor e5-large + gate 0.82).

Estes pares foram validados com dados reais do pipeline (scripts/validate_embedding_real.py)
e detectados como FP de negócio genuíno: 'arroz→açúcar', 'iogurte→leite em pó',
'miçanga→granulado', 'pipoca→manteiga'. A calibração do gate e5 para **0.82** (era 0.80
no MiniLM) corta esses itens que ficariam na faixa perigosa 0.80-0.82 de combined.

O teste cobre o ponto de decisão real (process_price_match): para cada FP, mockamos o
matcher semântico para entregar um combined na faixa 0.80-0.82 (o "antigo persistia") e
verificamos que o gate recalibrado **bloqueia** persistência E review.
"""
from unittest.mock import patch

import pytest

from services import collector

# Cada FP: (produto, ingrediente candidato estranho, rf_score gray-zone, semantic_score)
# combined = 0.6*(rf/100) + 0.4*semantic. Escolhemos rf 70 + semantic 0.30 → 0.42+0.12=0.54
# para FPs SEM homônimo; e um caso reforçado perto da faixa perigosa (0.80-0.82).
_FP_CASES = [
    # (desc, product_text, candidate_ingredient, rf, semantic)
    ("arroz nao vira acucar", "Arroz Branco Tipo 1 5kg", "Açúcar", 70.0, 0.30),
    ("iogurte nao vira leite em po", "Iogurte Natural Integral 900g", "Leite em Pó", 74.0, 0.30),
    ("micanga nao vira granulado", "Miçanga Colorida 200g", "Granulado Colorido", 72.0, 0.35),
    ("pipoca nao vira manteiga", "Pipoca de Micro-ondas Salgada 100g", "Manteiga", 70.0, 0.35),
]

# Faixa perigosa: combined entre 0.80 e 0.82 (com gate antigo 0.80 persistiria como FP).
# Para o teste, forçamos semantic de modo que combined fique DENTRO dessa faixa e o gate
# novo (0.82) bloqueie enquanto o gate velho (0.80) persistiria.
_FP_DANGEROUS_BAND = [
    # Forte RF (candidato rank alto) + semantic inflado → combined cai DENTRO da faixa
    # perigosa (0.80, 0.82), exatamente onde o gate antigo 0.80 persistiria como FP.
    ("arroz nao vira acucar (banda perigosa)", "Arroz Branco Tipo 1 5kg", "Açúcar", 90.0, 0.66),  # 0.54+0.264=0.804
    ("iogurte nao vira leite em po (banda perigosa)", "Iogurte Natural 900g", "Leite em Pó", 95.0, 0.60),  # 0.57+0.24=0.81
    ("micanga nao vira granulado (banda perigosa)", "Miçanga 200g", "Granulado Colorido", 90.0, 0.68),  # 0.54+0.272=0.812
]

MOCK_STORE = {
    "id": "store-fp-test",
    "name": "Loja FP Test",
    "type": "api_flyer",
    "tier": 1,
    "region": "Baixada Santista",
    "city": "Santos",
}


class _GateAwareFakeMatcher:
    """Mock matcher retornando semantic fixo e get_gate() = 0.82 (e5)."""

    def __init__(self, semantic_value: float):
        self._sem = semantic_value

    def get_similarity(self, product_text: str, ingredient: dict) -> float:
        return self._sem

    def combined_score(self, rf_score: float, semantic_score: float) -> float:
        return 0.6 * (rf_score / 100.0) + 0.4 * semantic_score

    def get_gate(self) -> float:
        return 0.82


def _fp_ingredient(canonical_name: str) -> list[dict]:
    return [{"canonical_name": canonical_name, "aliases": [], "search_terms": [], "exclude_terms": [], "brands": []}]


def _fake_feature_true(key: str, **kw):
    if key == "features.ai.enabled":
        return True
    return kw.get("default", True)


@pytest.mark.parametrize(
    "desc,product,candidate,rf,semantic",
    [
        (desc, product, candidate, rf, semantic)
        for desc, product, candidate, rf, semantic in _FP_CASES
    ],
)
def test_fp_semantic_baixo_nao_persiste(desc, product, candidate, rf, semantic):
    """FP com semantic baixo: combined < gate → sem upsert E sem review (descarte)."""
    with patch.object(collector, "get_matcher", return_value=_GateAwareFakeMatcher(semantic)), \
         patch("services.config.get_feature", side_effect=_fake_feature_true), \
         patch.object(collector, "upsert_price") as mock_up, \
         patch.object(collector, "insert_review_item") as mock_rev, \
         patch.object(collector, "rank_ingredients",
                      return_value=[(_fp_ingredient(candidate)[0], rf, "proximo_nome", candidate)]):
        entry = collector.process_price_match(
            MOCK_STORE, product, 12.9, "1kg", _fp_ingredient(candidate)
        )
    assert entry is None, f"FP deve ser descartado: {desc}"
    mock_up.assert_not_called()
    mock_rev.assert_not_called()


@pytest.mark.parametrize(
    "desc,product,candidate,rf,semantic",
    [
        (desc, product, candidate, rf, semantic)
        for desc, product, candidate, rf, semantic in _FP_DANGEROUS_BAND
    ],
)
def test_fp_na_banda_80_82_bloqueado_pelo_gate(desc, product, candidate, rf, semantic):
    """FP que cairia na faixa 0.80-0.82 (gate antigo 0.80 persistiria) é BLOQUEADO
    pelo gate e5 recalibrado 0.82 — sem upsert E sem review."""
    with patch.object(collector, "get_matcher", return_value=_GateAwareFakeMatcher(semantic)), \
         patch("services.config.get_feature", side_effect=_fake_feature_true), \
         patch.object(collector, "upsert_price") as mock_up, \
         patch.object(collector, "insert_review_item") as mock_rev, \
         patch.object(collector, "rank_ingredients",
                      return_value=[(_fp_ingredient(candidate)[0], rf, "proximo_nome", candidate)]):
        entry = collector.process_price_match(
            MOCK_STORE, product, 12.9, "1kg", _fp_ingredient(candidate)
        )
    assert entry is None, f"FP na banda perigosa deve ser bloqueado: {desc}"
    mock_up.assert_not_called()
    mock_rev.assert_not_called()


def test_gate_es_0_82_calibrado():
    """A calibração do gate e5-LARGE é 0.82 — é o que protege os FPs de negócio acima."""
    from parsers.semantic_matcher import SemanticMatcher

    assert SemanticMatcher.get_gate() == 0.82
