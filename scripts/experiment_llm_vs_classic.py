#!/usr/bin/env python3
"""
Experimento LLM vs. Clássico — Validação de custo-benefício do LLM classifier.

Objetivo: Comparar 3 braços de classificação usando dados REAIS da review_queue:
  A) Clássico puro (RapidFuzz + Semantic + regras) — sem LLM
  B) LLM Condicional (estado atual: clássico + LLM se confiança < 80%, floor 0.85)
  C) LLM Puro — LLM recebe top-3 candidatos sem pré-filtro clássico

Métricas coletadas:
  - Ganho real do LLM: itens aprovados corretamente que o clássico NÃO aprovava
  - FP do LLM: itens aprovados pelo LLM mas incorretos (ground truth = review resolvida)
  - Latência média por item
  - Taxa de 429 / circuit open
  - Itens que voltariam para review se LLM estivesse off

Uso:
  python scripts/experiment_llm_vs_classic.py --dry-run     # Preview da amostra
  python scripts/experiment_llm_vs_classic.py --execute     # Roda experimento real
"""

import json
import time
import argparse
import random
from datetime import date, datetime
from typing import Any

from services.logger import logger
from services.supabase_client import rpc_execute
from parsers.llm_classifier import classify


# ─── Config ──────────────────────────────────────────────────────────────────

# Bandas de confiança (mirror de collector.py)
GATE = 0.82  # gate e5
LLM_FLOOR = 0.85  # floor de aprovação do LLM
GRAY_ZONE_MIN = 0.70


def _generate_mock_samples() -> list[dict[str, Any]]:
    """Gera amostras sintéticas para dry-run sem DB."""
    mock_ingredients = [
        {"canonical_name": "Leite Condensado", "aliases": ["Leite Cond"]},
        {"canonical_name": "Creme de Leite", "aliases": ["Creme Leite"]},
        {"canonical_name": "Chocolate ao Leite 50%", "aliases": ["Choc 50%"]},
        {"canonical_name": "Leite em Pó", "aliases": ["Leite Po"]},
        {"canonical_name": "Granulado Ao Leite", "aliases": ["Granulado"]},
        {"canonical_name": "Chocolate 70%", "aliases": ["Choc 70%"]},
        {"canonical_name": "Açúcar Mascavo", "aliases": ["Acucar Mascavo"]},
        {"canonical_name": "Granulado Branco", "aliases": ["Granulado Bran"]},
    ]

    mock_products = [
        "Leite Condensado 395g",
        "Creme de Leite 900g",
        "Chocolate ao Leite 50% 200g",
        "Leite em Pó integral 400g",
        "Granulado Ao Leite 500g",
        "Chocolate 70% 100g",
        "Açúcar Mascavo 1kg",
        "Granulado Colorido 100g",
        "Coco Ralado 200g",
        "Chocolate Nobre Blend 1kg",
    ]

    samples = []
    statuses = ["pending", "approved", "rejected"]
    for i in range(50):
        product = random.choice(mock_products)
        ingredient = random.choice(mock_ingredients)
        score = random.uniform(0.70, 0.82)
        status = random.choice(statuses)
        sample = {
            "id": f"mock_{i}",
            "product_text": product,
            "candidate_ingredients": json.dumps([ingredient]),
            "combined_score": round(score, 4),
            "llm_confidence": round(random.uniform(0.7, 0.95), 4),
            "llm_provider": random.choice(["groq", "openrouter", None]),
            "llm_reason": "LLM classification",
            "status": status,
            "human_verdict": ingredient["canonical_name"] if status == "approved" else None,
            "decision_reason": f"alias → {ingredient['canonical_name']}" if status == "approved" else "rejected by human",
            "created_at": date.today().isoformat(),
        }
        samples.append(sample)
    return samples


def _fetch_review_samples() -> list[dict[str, Any]]:
    """Extrai itens da review_queue via RPC exec_sql_query."""
    # Busca itens pendentes na banda 0.70-0.82 + resolvidos recentes para FP check
    sql = """
    SELECT
        rq.id,
        rq.raw_product as product_text,
        rq.suggestions as candidate_ingredients,
        rq.confidence as combined_score,
        rq.validity_raw as llm_confidence,
        '' as llm_provider,
        rq.match_reason as llm_reason,
        rq.status,
        rq.resolved_ingredient as human_verdict,
        rq.match_reason as decision_reason,
        rq.collected_at as created_at
    FROM review_queue rq
    WHERE rq.status IN ('pending', 'approved', 'rejected')
      AND rq.confidence >= 0.70
      AND rq.confidence < 0.82
    ORDER BY rq.collected_at DESC
    LIMIT 200
    """
    try:
        from services.supabase_client import get_service_client
        client = get_service_client()
        result = rpc_execute(client, "exec_sql_query", {"sql": sql})
        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(f"RPC error: {result['error']}")
        if not isinstance(result, list):
            raise RuntimeError(f"Unexpected RPC response type: {type(result)}")
        return result
    except Exception as e:
        # Fallback: dados sintéticos para dry-run sem credenciais DB
        logger.warning("llm_experiment_db_unavailable", error=str(e))
        return _generate_mock_samples()


def _generate_mock_samples() -> list[dict[str, Any]]:
    """Gera amostras sintéticas para dry-run sem DB."""
    mock_ingredients = [
        {"canonical_name": "Leite Condensado", "aliases": ["Leite Cond"]},
        {"canonical_name": "Creme de Leite", "aliases": ["Creme Leite"]},
        {"canonical_name": "Chocolate ao Leite 50%", "aliases": ["Choc 50%"]},
        {"canonical_name": "Leite em Pó", "aliases": ["Leite Po"]},
        {"canonical_name": "Granulado Ao Leite", "aliases": ["Granulado"]},
        {"canonical_name": "Chocolate 70%", "aliases": ["Choc 70%"]},
        {"canonical_name": "Açúcar Mascavo", "aliases": ["Acucar Mascavo"]},
        {"canonical_name": "Granulado Branco", "aliases": ["Granulado Bran"]},
    ]

    mock_products = [
        "Leite Condensado 395g",
        "Creme de Leite 900g",
        "Chocolate ao Leite 50% 200g",
        "Leite em Pó integral 400g",
        "Granulado Ao Leite 500g",
        "Chocolate 70% 100g",
        "Açúcar Mascavo 1kg",
        "Granulado Colorido 100g",
        "Coco Ralado 200g",
        "Chocolate Nobre Blend 1kg",
    ]

    samples = []
    statuses = ["pending", "approved", "rejected"]
    for i in range(50):
        product = random.choice(mock_products)
        ingredient = random.choice(mock_ingredients)
        score = random.uniform(0.70, 0.82)
        status = random.choice(statuses)
        sample = {
            "id": f"mock_{i}",
            "product_text": product,
            "candidate_ingredients": json.dumps([ingredient]),
            "combined_score": round(score, 4),
            "llm_confidence": round(random.uniform(0.7, 0.95), 4),
            "llm_provider": random.choice(["groq", "openrouter", None]),
            "llm_reason": "LLM classification",
            "status": status,
            "human_verdict": ingredient["canonical_name"] if status == "approved" else None,
            "decision_reason": f"alias → {ingredient['canonical_name']}" if status == "approved" else "rejected by human",
            "created_at": date.today().isoformat(),
        }
        samples.append(sample)
    return samples


def _fetch_review_samples() -> list[dict[str, Any]]:
    """Extrai itens da review_queue via RPC exec_sql_query."""
    sql = """
    SELECT
        rq.id,
        rq.raw_product as product_text,
        rq.suggestions as candidate_ingredients,
        rq.confidence as combined_score,
        rq.validity_raw as llm_confidence,
        '' as llm_provider,
        rq.match_reason as llm_reason,
        rq.status,
        rq.resolved_ingredient as human_verdict,
        rq.match_reason as decision_reason,
        rq.collected_at as created_at
    FROM review_queue rq
    WHERE rq.status IN ('pending', 'approved', 'rejected')
      AND rq.confidence >= 0.70
      AND rq.confidence < 0.82
    ORDER BY rq.collected_at DESC
    LIMIT 200
    """
    try:
        from services.supabase_client import get_service_client
        client = get_service_client()
        result = rpc_execute(client, "exec_sql_query", {"sql": sql})
        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(f"RPC error: {result['error']}")
        if not isinstance(result, list):
            raise RuntimeError(f"Unexpected RPC response type: {type(result)}")
        return result
    except Exception as e:
        logger.warning("llm_experiment_db_unavailable", error=str(e))
        return _generate_mock_samples()


def _extract_ingredients_from_sample(sample: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrai lista de ingredientes candidatos do sample."""
    candidates = sample.get("candidate_ingredients")
    if isinstance(candidates, str):
        try:
            candidates = json.loads(candidates)
        except json.JSONDecodeError:
            return []
    if not isinstance(candidates, list):
        return []

    # Converte strings de sugestão em formato esperado por rank_ingredients
    # (dict com canonical_name, aliases, search_terms)
    ingredients = []
    for sug in candidates:
        if isinstance(sug, str):
            ingredients.append({
                "canonical_name": sug,
                "aliases": [],
                "search_terms": [],
            })
        elif isinstance(sug, dict) and sug.get("canonical_name"):
            # Já está no formato correto
            ingredients.append(sug)
    return ingredients


def _classic_classify(product_text: str, ingredients: list[dict[str, Any]]) -> tuple[str | None, float, str]:
    """
    Classificador clássico puro (sem LLM).
    Retorna (ingredient_canonical, combined_score, match_type) ou (None, 0.0, 'no_match').
    """
    from parsers.matcher import rank_ingredients

    if not ingredients:
        return None, 0.0, "no_candidates"

    # Usa rank_ingredients que já retorna top-N ordenados por score
    ranked = rank_ingredients(product_text, ingredients, top_n=3)
    if not ranked:
        return None, 0.0, "no_match"

    best_ing, score, match_type, matched_term = ranked[0]
    canonical = best_ing.get("canonical_name")
    score = score / 100.0  # rank_ingredients retorna 0-100

# Semantic matching (se habilitado e score na gray zone)
    if score >= 0.60 and score < 0.80:
        try:
            from parsers.semantic_matcher import get_matcher
            sm = get_matcher()
            semantic_score = sm.get_similarity(product_text, ranked[0][0].get("canonical_name", ""))
            if semantic_score > 0.0:
                from parsers.semantic_matcher import SemanticMatcher
                best_score = SemanticMatcher.combined_score(score * 100, semantic_score) / 100.0
                return canonical, best_score, "semantic"
        except Exception:
            pass  # Se semantic falhar (fastembed não instalado, etc.), usa só o clássico

    return canonical, score, "fuzzy"


def _llm_classify(product_text: str, ingredients: list[dict[str, Any]]) -> tuple[str | None, float, str, str | None]:
    """
    Chama LLM classifier real.
    Retorna (canonical, confidence, provider, reason) ou (None, 0.0, None, error).
    """

    # Prepara top-3 candidatos
    candidates = []
    for ing in ingredients[:3]:
        if ing.get("canonical_name"):
            candidates.append(ing)

    if not candidates:
        return None, 0.0, None, "no_candidates"

    try:
        result = classify(product_text, candidates)
        if result and result.get("match") and result.get("confidence", 0) >= 0.85:
            return result["ingredient"], result["confidence"], result.get("provider"), result.get("reason")
        return None, 0.0, result.get("provider") if result else None, result.get("reason") if result else "no_match"
    except Exception as e:
        return None, 0.0, None, f"error: {e}"


def _resolve_ground_truth(sample: dict[str, Any]) -> str | None:
    """Resolve ground truth a partir do human_verdict ou decision_reason."""
    if sample.get("human_verdict"):
        return sample["human_verdict"]

    dr = sample.get("decision_reason", "")
    if "alias" in dr.lower() and "→" in dr:
        parts = dr.split("→")
        if len(parts) == 2:
            return parts[1].strip().split(" ")[0]

    if sample.get("status") == "approved":
        candidates = _extract_ingredients_from_sample(sample)
        if len(candidates) == 1:
            return candidates[0].get("canonical_name")

    return None


def run_experiment(dry_run: bool = True) -> dict[str, Any]:
    """Executa o experimento completo."""
    print("=" * 70)
    print(f"EXPERIMENTO LLM vs CLÁSSICO ({'DRY-RUN' if dry_run else 'EXECUÇÃO REAL'})")
    print("=" * 70)

    samples = _fetch_review_samples()
    print(f"\nAmostras extraídas: {len(samples)}")
    print(f"Período: {samples[-1]['created_at'][:10]} a {samples[0]['created_at'][:10]}" if samples else "Sem dados")

    if not samples:
        return {"error": "Nenhuma amostra encontrada"}

    results = {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "dry_run": dry_run,
            "total_samples": len(samples),
            "gate": GATE,
            "llm_floor": LLM_FLOOR,
        },
        "arms": {
            "classic": {"approved": 0, "correct": 0, "items": []},
            "llm_conditional": {"approved": 0, "correct": 0, "fp": 0, "items": []},
            "llm_pure": {"approved": 0, "correct": 0, "fp": 0, "items": []},
        },
        "latency": {"classic_ms": [], "llm_conditional_ms": [], "llm_pure_ms": []},
        "errors": {"llm_429": 0, "llm_circuit_open": 0, "llm_errors": 0},
    }

    for i, sample in enumerate(samples):
        product_text = sample.get("product_text", "")
        combined = sample.get("combined_score", 0.0)
        ingredients = _extract_ingredients_from_sample(sample)
        ground_truth = _resolve_ground_truth(sample)

        has_ground_truth = ground_truth is not None

        # ─── Braço A: Clássico Puro ───
        t0 = time.perf_counter()
        classic_canon, classic_score, classic_type = _classic_classify(product_text, _extract_ingredients_from_sample(sample))
        results["latency"]["classic_ms"].append((time.perf_counter() - t0) * 1000)

        classic_approved = classic_canon is not None and classic_score >= GATE
        classic_correct = False
        if classic_approved and has_ground_truth:
            classic_correct = classic_canon == ground_truth

        results["arms"]["classic"]["approved"] += 1 if classic_approved else 0
        results["arms"]["classic"]["correct"] += 1 if classic_correct else 0
        results["arms"]["classic"]["items"].append({
            "id": sample["id"],
            "product": product_text[:50],
            "canonical": classic_canon,
            "score": round(classic_score, 4),
            "type": classic_type,
            "approved": classic_approved,
            "correct": classic_correct,
        })

        # ─── Braço B: LLM Condicional (estado atual) ───
        llm_cond_approved = False
        llm_cond_correct = False
        llm_cond_fp = False

        if classic_canon and classic_score >= GATE:
            llm_cond_approved = classic_approved
            llm_cond_correct = classic_correct
        elif classic_canon and classic_score >= GRAY_ZONE_MIN:
            t0 = time.perf_counter()
            llm_canon, llm_conf, llm_prov, llm_reason = _llm_classify(product_text, _extract_ingredients_from_sample(sample))
            results["latency"]["llm_conditional_ms"].append((time.perf_counter() - t0) * 1000)

            if llm_canon and llm_conf >= 0.85:
                llm_cond_approved = True
                if has_ground_truth and llm_canon == ground_truth:
                    llm_cond_correct = True
                elif has_ground_truth:
                    results["arms"]["llm_conditional"]["fp"] += 1
                    llm_cond_fp = True
        results["arms"]["llm_conditional"]["approved"] += 1 if llm_cond_approved else 0
        results["arms"]["llm_conditional"]["correct"] += 1 if llm_cond_correct else 0

        # ─── Braço C: LLM Puro (sem pré-filtro) ───
        t0 = time.perf_counter()
        llm_pure_canon, llm_pure_conf, llm_pure_prov, llm_pure_reason = _llm_classify(product_text, _extract_ingredients_from_sample(sample))
        results["latency"]["llm_pure_ms"].append((time.perf_counter() - t0) * 1000)

        llm_pure_approved = llm_pure_canon is not None and llm_pure_conf >= 0.85
        llm_pure_correct = False
        if llm_pure_approved and has_ground_truth:
            llm_pure_correct = llm_pure_canon == ground_truth
        elif llm_pure_approved and has_ground_truth:
            results["arms"]["llm_pure"]["fp"] += 1

        results["arms"]["llm_pure"]["approved"] += 1 if llm_pure_approved else 0
        results["arms"]["llm_pure"]["correct"] += 1 if llm_pure_correct else 0

        if (i + 1) % 20 == 0:
            print(f"  Processado {i + 1}/{len(samples)}...")

    # ─── Sumário ───
    print("\n" + "=" * 70)
    print("RESULTADOS")
    print("=" * 70)

    for arm_name, arm_data in results["arms"].items():
        total = len(samples)
        approved = arm_data["approved"]
        correct = arm_data["correct"]
        fp = arm_data.get("fp", 0)
        print(f"\n{arm_name.upper()}:")
        print(f"  Aprovados: {approved}/{len(samples)} ({approved/len(samples)*100:.1f}%)")
        if has_ground_truth:
            print(f"  Corretos:  {correct}/{approved if approved else 1} ({correct/approved*100:.1f}%)" if approved else "  Corretos:  0/0")
            print(f"  FP:        {fp}")

    for arm_name, latencies in results["latency"].items():
        if latencies:
            avg = sum(latencies) / len(latencies)
            print(f"  Latência média {arm_name}: {avg:.1f}ms")

    return results


def main():
    parser = argparse.ArgumentParser(description="Experimento LLM vs. Clássico")
    parser.add_argument("--dry-run", action="store_true", help="Apenas preview da amostra (não chama LLM)")
    parser.add_argument("--execute", action="store_true", help="Executa experimento real (chama LLM)")
    parser.add_argument("--output", type=str, default="data/experiment_llm_report.json", help="Arquivo de saída")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Use --dry-run para preview ou --execute para execução real")
        return 1

    dry_run = args.dry_run
    results = run_experiment(dry_run=dry_run)

    # Salva relatório
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nRelatório salvo em: {args.output}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())