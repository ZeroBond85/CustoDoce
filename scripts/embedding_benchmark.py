#!/usr/bin/env python3
"""
Benchmark de modelos de embedding multilíngue para decisão de acurácia pt-BR.
Hardware-independente (accuracy@1, MRR, estabilidade do gate combined=0.80).
Uso: python scripts/embedding_benchmark.py
"""
from __future__ import annotations
import json
import random
import re
import resource
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.supabase_client import get_service_client  # noqa: E402

# ============================================================
# CONFIGURAÇÃO DO BENCHMARK
# ============================================================
# Modelos suportados pelo fastembed 0.8.0 (multilíngue)
CANDIDATE_MODELS = [
    {
        "name": "paraphrase-multilingual-MiniLM-L12-v2",
        "model_name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "dim": 384,
        "needs_prefix": False,
        "notes": "Baseline 2019, multilíngue ~50 idiomas",
    },
    {
        "name": "paraphrase-multilingual-mpnet-base-v2",
        "model_name": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        "dim": 768,
        "needs_prefix": False,
        "notes": "STS-simétrica, melhor que MiniLM, multilíngue ~50 idiomas",
    },
    {
        "name": "multilingual-e5-large",
        "model_name": "intfloat/multilingual-e5-large",
        "dim": 1024,
        "needs_prefix": True,
        "notes": "Melhor acurácia viável CPU (560M, ~100 idiomas), requer prefixes query:/passage:",
    },
    {
        "name": "jina-embeddings-v2-base-de",
        "model_name": "jinaai/jina-embeddings-v2-base-de",
        "dim": 768,
        "needs_prefix": False,
        "notes": "Multilingual (German, English), 8k tokens - pode ajudar pt-BR",
    },
    {
        "name": "jina-embeddings-v3",
        "model_name": "jinaai/jina-embeddings-v3",
        "dim": 1024,
        "needs_prefix": False,
        "notes": "Multi-tarefa, ~100 idiomas, 1024/8192 tokens, CC-BY-NC-4.0",
    },
]

N_POSITIVOS = 300
N_NEGATIVOS = 200
SEED = 42
random.seed(SEED)
np.random.seed(SEED)

# Ingredientes que NÃO devem aparecer como substring parcial (falsos positivos)
INGREDIENTES_AMBIGUOS = {
    "Manteiga",  # aparece em "Manteiga Gordura Vegetal", "Alimento Manteiga"
    "Fermento",  # aparece em "Fermento Químico", "Fermento Biológico"
    "Chocolate",  # genérico demais
    "Açúcar",  # genérico demais
    "Leite",  # genérico demais
    "Creme",  # genérico demais
    "Cacau",  # aparece em "Chocolate 70% Cacau"
    "Baunilha",  # aparece em "Sabor Baunilha", "Essência de Baunilha"
}

def cos_sim(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    val = float(np.dot(a, b) / (na * nb))
    # Embeddings degenerados (NaN/linf) nao devem dominar o ranking
    if np.isnan(val) or np.isinf(val) or val < 0:
        return 0.0
    return val

def peak_rss_bytes() -> int:
    """Pico de RSS do processo (Linux/macOS) via getrusage. Em kB no Linux."""
    try:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss é kB no Linux, bytes no macOS
        if sys.platform == "darwin":
            return ru.ru_maxrss
        return ru.ru_maxrss * 1024
    except Exception:
        return 0

def format_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024.0:
            return f"{n:.2f}{unit}"
        n /= 1024.0
    return f"{n:.2f}TB"

def ingredient_in_product(ingredient: str, product: str) -> bool:
    """Verifica se o ingrediente aparece no produto como palavra completa (case-insensitive)."""
    ing_lower = ingredient.lower()
    prod_lower = product.lower()
    # Word boundary check: ingredient must appear as whole word(s)
    pattern = r'\b' + re.escape(ing_lower) + r'\b'
    return bool(re.search(pattern, prod_lower))

def load_labeled_data() -> tuple[list[dict], list[dict]]:
    """
    Retorna (positivos, negativos) onde cada item é:
    {"text": product_text, "ingredient_id": canonical_name, "ingredient_name": canonical_name}
    """
    client = get_service_client()

    # 1) Positivos: prices com alta confiança E ingrediente aparece no texto do produto
    prices = client.table("prices").select(
        "raw_product, ingredient_id, confidence"
    ).gte("confidence", 0.9).limit(5000).execute().data

    pos_pairs = []
    for p in prices:
        ing = p.get("ingredient_id")
        prod = p.get("raw_product")
        if ing and prod and ingredient_in_product(ing, prod):
            pos_pairs.append({
                "text": prod,
                "ingredient_id": ing,
                "ingredient_name": ing,
            })

    print(f"[data] Pares limpos (ingrediente no produto): {len(pos_pairs)}")

    # 2) Negativos: review_queue rejected (human verified non-matches)
    rejected = client.table("review_queue").select(
        "raw_product, top3, status"
    ).eq("status", "rejected").limit(500).execute().data

    neg_pairs = []
    for r in rejected:
        if r.get("raw_product") and r.get("top3"):
            top = r["top3"][0]
            neg_pairs.append({
                "text": r["raw_product"],
                "ingredient_id": top["canonical_name"],
                "ingredient_name": top["canonical_name"],
                "type": "rejected",
            })

    # 3) Distratores: para alguns positivos, pega ingrediente ERRADO
    all_ings = client.table("ingredients").select("id, canonical_name").eq("active", True).execute().data
    all_canonicals = [i["canonical_name"] for i in all_ings]

    for p in pos_pairs[:min(50, len(pos_pairs))]:
        wrong = [c for c in all_canonicals if c != p["ingredient_id"]]
        if wrong:
            chosen = random.choice(wrong)
            neg_pairs.append({
                "text": p["text"],
                "ingredient_id": chosen,
                "ingredient_name": chosen,
                "type": "distractor",
            })

    # Amostragem
    if len(pos_pairs) > N_POSITIVOS:
        pos_pairs = random.sample(pos_pairs, N_POSITIVOS)
    if len(neg_pairs) > N_NEGATIVOS:
        neg_pairs = random.sample(neg_pairs, N_NEGATIVOS)

    print(f"[data] positivos finais: {len(pos_pairs)}, negativos: {len(neg_pairs)}")
    return pos_pairs, neg_pairs

def get_all_ingredients() -> list[dict]:
    """Retorna todos ingredientes ativos com canonical + aliases + search_terms"""
    client = get_service_client()
    ings = client.table("ingredients").select(
        "id, canonical_name, aliases, search_terms"
    ).eq("active", True).execute().data
    return ings

def run_candidate(
    model_cfg: dict,
    positives: list[dict],
    negatives: list[dict],
    all_ings: list[dict],
    debug_samples: int = 5,
) -> dict:
    """Roda um modelo candidato e retorna métricas.

    Usa a mesma abordagem do SemanticMatcher real: max(sim) por ingrediente,
    NÃO prototype averaging.
    """
    from collections import defaultdict

    from fastembed import TextEmbedding

    model_name = model_cfg["model_name"]
    needs_prefix = model_cfg.get("needs_prefix", False)
    print(f"\n[model] Carregando {model_name}...")
    t0 = time.monotonic()
    try:
        model = TextEmbedding(model_name=model_name)
    except Exception as e:
        print(f"[model] ERRO ao carregar {model_name}: {e}")
        return {"name": model_cfg["name"], "error": str(e)}
    load_seconds = time.monotonic() - t0

    # 1) Embed todos os textos de ingredientes (canonical + aliases + search_terms)
    #    Cada texto individual fica mapeado ao seu canonical_name (ingredient_id)
    #    Mede também o uso de memória somente do modelo (isolado)
    ing_texts: list[str] = []
    ing_canonicals: list[str] = []  # parallel: canonical_name para cada texto
    for ing in all_ings:
        canonical = ing["canonical_name"]
        texts = [canonical]
        if ing.get("aliases"):
            texts.extend(ing["aliases"])
        if ing.get("search_terms"):
            texts.extend(ing["search_terms"])
        for t in texts:
            if needs_prefix:
                t = "passage: " + t
            ing_texts.append(t)
            ing_canonicals.append(canonical)

    print(f"[model] Embedding {len(ing_texts)} textos de ingredientes...")
    t1 = time.monotonic()
    ing_embs = list(model.embed(ing_texts))
    t2 = time.monotonic()
    rss_after_ing = peak_rss_bytes()
    if len(ing_embs) != len(ing_texts):
        return {"name": model_cfg["name"], "error": "ingredient embedding count mismatch"}

    # Agrupa embeddings por canonical_name (cada um normalizado)
    ing_emb_by_canonical: dict[str, list[np.ndarray]] = defaultdict(list)
    for emb, canonical in zip(ing_embs, ing_canonicals, strict=False):
        norm = np.linalg.norm(emb)
        if norm > 0:
            ing_emb_by_canonical[canonical].append(emb / norm)

    canonicals_sorted = sorted(ing_emb_by_canonical.keys())

    # 2) Embed produtos (positivos + negativos)
    all_products = positives + negatives
    prod_texts = [p["text"] for p in all_products]
    if needs_prefix:
        prod_texts = ["query: " + t for t in prod_texts]
    print(f"[model] Embedding {len(prod_texts)} produtos...")
    t3 = time.monotonic()
    prod_embs = list(model.embed(prod_texts))
    t4 = time.monotonic()
    rss_peak = peak_rss_bytes()
    if len(prod_embs) != len(prod_texts):
        return {"name": model_cfg["name"], "error": "product embedding count mismatch"}

    prod_embs_norm = [e / np.linalg.norm(e) if np.linalg.norm(e) > 0 else e for e in prod_embs]

    # 3) Para cada produto: max(sim) contra cada canonical → ranking
    def rank_product(prod_emb_norm: np.ndarray) -> list[tuple[str, float]]:
        scores = []
        for canonical in canonicals_sorted:
            embs = ing_emb_by_canonical[canonical]
            max_sim = max(cos_sim(prod_emb_norm, e) for e in embs)
            scores.append((canonical, max_sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    # 4) Métricas nos positivos
    correct_at_1 = 0
    correct_at_3 = 0
    correct_at_5 = 0
    mrr_sum = 0.0
    pos_skipped = 0

    # Debug: imprimir top-5 para alguns positivos
    debug_pos = min(debug_samples, len(positives))

    for idx, p in enumerate(positives):
        prod_emb = prod_embs_norm[idx]
        true_id = p["ingredient_id"]
        ranking = rank_product(prod_emb)

        top_ids = [r[0] for r in ranking[:5]]
        if not top_ids:
            # Modelo produziu ranking vazio p/ este produto (emb degenerado).
            # Conta como miss; nao derruba o benchmark inteiro.
            pos_skipped += 1
            continue
        if top_ids[0] == true_id:
            correct_at_1 += 1
        if true_id in top_ids[:3]:
            correct_at_3 += 1
        if true_id in top_ids[:5]:
            correct_at_5 += 1
        for rank, (cid, _) in enumerate(ranking, 1):
            if cid == true_id:
                mrr_sum += 1.0 / rank
                break

        if idx < debug_pos:
            print(f"  [DEBUG] Produto: {p['text'][:60]!r}")
            print(f"          True: {true_id!r}")
            for r in ranking[:3]:
                marker = " ✓" if r[0] == true_id else ""
                print(f"          #{ranking.index(r)+1}: {r[0]!r} (sim={r[1]:.4f}){marker}")

    n_pos = len(positives)
    acc1 = correct_at_1 / n_pos if n_pos else 0.0
    acc3 = correct_at_3 / n_pos if n_pos else 0.0
    acc5 = correct_at_5 / n_pos if n_pos else 0.0
    mrr = mrr_sum / n_pos if n_pos else 0.0

    # 5) Métricas nos negativos
    neg_correct = 0
    neg_skipped = 0
    for idx, p in enumerate(negatives):
        prod_emb = prod_embs_norm[n_pos + idx]
        true_id = p["ingredient_id"]
        ranking = rank_product(prod_emb)
        if not ranking:
            neg_skipped += 1
            continue
        if ranking[0][0] != true_id:
            neg_correct += 1

    n_neg_eff = len(negatives) - neg_skipped
    neg_acc = neg_correct / n_neg_eff if n_neg_eff else 0.0

    n_all = len(all_products)
    n_neg = len(negatives)
    embed_seconds_total = (t2 - t1) + (t4 - t3)
    ing_seconds_per_1000 = (t2 - t1) / len(ing_texts) * 1000 if ing_texts else 0.0
    # Throughput de PRODUTOS puro (bottleneck do scrape diário): exclui o tempo de
    # ingredientes, que e amortizado (embed 1x por dia). Gate real do scrape.
    prod_seconds_per_1000 = (t4 - t3) / n_all * 1000 if n_all else 0.0

    # Extrapolação: ~2.500 produtos/dia no scrape completo (tiers 1/2a/3)
    # Mais ~2.000 texto de ingredientes (27 ingredientes x alias/search_terms)
    EXTRAPOLATE_PRODUCTS = 2500
    EXTRAPOLATE_INGREDIENTS = 2000
    ing_extrap_s = (t2 - t1) / len(ing_texts) * EXTRAPOLATE_INGREDIENTS if ing_texts else 0.0
    prod_extrap_s = (t4 - t3) / n_all * EXTRAPOLATE_PRODUCTS if n_all else 0.0
    extrapolated_total_s = ing_extrap_s + prod_extrap_s
    extrapolated_total_min = extrapolated_total_s / 60.0

    return {
        "model": model_cfg["name"],
        "dim": model_cfg["dim"],
        "accuracy_at_1": round(acc1, 4),
        "accuracy_at_3": round(acc3, 4),
        "accuracy_at_5": round(acc5, 4),
        "mrr": round(mrr, 4),
        "neg_accuracy": round(neg_acc, 4),
        "n_positivos": n_pos,
        "n_negativos": n_neg,
        "n_neg_skipped": neg_skipped,
        "load_seconds": round(load_seconds, 1),
        "hours_wall": None,
        "peak_rss_bytes": rss_peak,
        "peak_rss_mb": round(rss_peak / (1024 * 1024), 1),
        "prod_seconds_per_1000": round(prod_seconds_per_1000, 2),
        "ing_seconds_per_1000": round(ing_seconds_per_1000, 2),
        "embed_seconds_total": round(embed_seconds_total, 1),
        "ing_extrap_s": round(ing_extrap_s, 1),
        "prod_extrap_s": round(prod_extrap_s, 1),
        "extrapolated_total_min": round(extrapolated_total_min, 1),
        "extrapolated_total_s": round(extrapolated_total_s, 1),
        "n_products_embedded": n_all,
    }


def main() -> int:
    print("=" * 60)
    print("EMBEDDING BENCHMARK — Acurácia pt-BR (CustoDoce)")
    print("=" * 60)

    print("\n[1/3] Carregando dataset rotulado do Supabase...")
    positives, negatives = load_labeled_data()
    all_ings = get_all_ingredients()
    print(f"[data] Ingredientes ativos: {len(all_ings)}")

    print("\n[2/3] Rodando candidatos...")
    results = []
    for cfg in CANDIDATE_MODELS:
        res = run_candidate(cfg, positives, negatives, all_ings)
        results.append(res)
        if "error" not in res:
            print(f"  {cfg['name']}: acc@1={res['accuracy_at_1']:.4f} MRR={res['mrr']:.4f} "
                  f"neg_acc={res['neg_accuracy']:.4f} RSS={res['peak_rss_mb']}MB "
                  f"prod_s/1000={res['prod_seconds_per_1000']} ing_s/1000={res['ing_seconds_per_1000']} "
                  f"extrap={res['extrapolated_total_min']}min load={res['load_seconds']}s")
        else:
            print(f"  {cfg['name']}: ERRO - {res['error']}")

    print("\n" + "=" * 95)
    print("RESULTADO FINAL — Acurácia por Modelo")
    print("=" * 95)
    print(f"{'Modelo':<45} {'Dim':>5} {'Acc@1':>8} {'Acc@3':>8} {'Acc@5':>8} {'MRR':>8} {'NegAcc':>8} {'RSS(MB)':>9} {'prod s/1000':>11} {'Extrap(min)':>11}")
    print("-" * 95)
    for r in results:
        if "error" in r:
            print(f"{r['name']:<45} {'ERR':>5} {'-':>8} {'-':>8} {'-':>8} {'-':>8} {'-':>8} {'-':>9} {'-':>11} {'-':>11}")
        else:
            print(f"{r['model']:<45} {r['dim']:>5} {r['accuracy_at_1']:>8.4f} {r['accuracy_at_3']:>8.4f} {r['accuracy_at_5']:>8.4f} {r['mrr']:>8.4f} {r['neg_accuracy']:>8.4f} {r['peak_rss_mb']:>9.1f} {r['prod_seconds_per_1000']:>11.2f} {r['extrapolated_total_min']:>11.1f}")

    out = ROOT / "data" / "embedding_benchmark_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n[save] Resultados salvos em {out}")

    valid = [r for r in results if "error" not in r]
    if valid:
        best = max(valid, key=lambda x: x["accuracy_at_1"])
        print(f"\n>>> RECOMENDAÇÃO (acurácia): {best['model']} (acc@1={best['accuracy_at_1']:.4f})")
        print("\n=== Checagem de limites da máquina (gate de decisão) ===")
        print("  Limites duros: pico RSS <= 4.5GB | embeddings scrape completo <= 20min | prod s/1000 <= 45")
        for r in sorted(valid, key=lambda x: x["accuracy_at_1"], reverse=True):
            rss_ok = r.get("peak_rss_mb", 0) <= 4.5 * 1024
            time_ok = r.get("extrapolated_total_min", 1e9) <= 20.0
            s1000_ok = r.get("prod_seconds_per_1000", 1e9) <= 45.0
            status = "PASSA" if (rss_ok and time_ok and s1000_ok) else "FALHA"
            print(f"  [{status}] {r['model']:<45} RSS={r.get('peak_rss_mb',0):.0f}MB "
                  f"extrap={r.get('extrapolated_total_min',0):.1f}min prod_s/1000={r.get('prod_seconds_per_1000',0):.1f}")
        print("\n  >>> Decisão final = melhor acurácia que cabe na máquina medida (Fase 0B no runner).")
        print("  >>> Validar na Fase 0B (runner real) antes de decidir.")

    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())