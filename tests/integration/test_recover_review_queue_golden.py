"""Teste integration: golden de 300 casos reais da review_queue.

Valida a decisão de rejeição do recover_review_queue contra os ingredientes
ativos REAIS do Supabase (fonte da verdade em runtime via get_active_ingredients).

Motivo de estar aqui (não em unit): a regra #3 exige marcação @pytest.mark.integration
para testes com Supabase real — antes rodava em tests/unit fazendo rede real,
causando flake de DNS no CI (httpx.ConnectError Name or service not known).
"""

import json
from pathlib import Path

import pytest

from scripts import recover_review_queue as rq
from services.config_db import get_active_ingredients


@pytest.mark.integration
def test_reject_false_positives_golden_300():
    """Golden de 300 casos reais valida a decisão de rejeição.

    Casos sem match (falsos-positivos do matcher antigo) devem ser rejeitados;
    casos com match devem ser preservados. Fixture gerada de dados reais da
    review_queue (150 reject + 150 keep, estratificado por loja).
    """
    fixture = json.loads(
        Path("tests/fixtures/golden_review_queue_reject.json").read_text(encoding="utf-8")
    )
    ingredients = get_active_ingredients()
    assert ingredients, "ingredientes ativos do Supabase não podem ser vazios"

    fp_ids = []
    for case in fixture:
        product = case["raw_product"]
        ing, score, _ = rq.match_ingredient(product, ingredients, threshold=60.0)
        should_reject = not ing or score < 60.0
        if should_reject != case["expected_reject"]:
            fp_ids.append((product, case["expected_reject"], should_reject))
    assert not fp_ids, f"Golden divergiu em {len(fp_ids)} casos: {fp_ids[:5]}"
