"""Limpeza de Falsos Positivos (FPs) + dados de teste na tabela `prices`.

Segue AGENTS.md regra #18 (fluxo correto): client nativo PostgREST
(porta 443), dry-run antes, validação pós-aplicação. Audit item #2:
NENHUMA f-string SQL — filtros 100% via query builder (`.or_`, `.in_`,
`count="exact"`), eliminando a classe S608/B608 (SQL injection por
interpolação) deste script.

Uso:
    python scripts/cleanup_price_fps.py --dry-run    # só mostra o que seria apagado
    python scripts/cleanup_price_fps.py --execute    # aplica o DELETE
"""

import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.supabase_client import get_service_client  # noqa: E402

# Tokens de contexto NÃO-alimentar (embalagem/decoração/artesanato) que causam
# FPs do matcher — espelha _PACKAGING_TOKENS e exclude_terms.
_NON_FOOD_PATTERNS = [
    "%papel%",
    "%caixa%",
    "%embalagem%",
    "%chenille%",
    "%pelúcia%",
    "%folha%",
    "%forminha%",
    "%lembrancinha%",
    "%decorativo%",
    "%artesanato%",
    "%blister%",
    "%haste%",
    "%brinquedo%",
]

# Ingredientes de teste que não devem existir em produção
_TEST_INGREDIENTS = ["_test_hist_unique_ing"]

# Ingredientes órfãos: existiam em versões antigas do ingredients.yaml e foram
# removidos/renomeados. Qualquer preço associado a eles é dado morto.
_ORPHAN_INGREDIENTS = ["Leite Condensado"]

# Produtos LEGÍTIMOS que contêm tokens de embalagem no nome mas são alimentos
# reais (ex: "Açúcar Confeiteiro Snow Sugar Embalagem 500g"). Whitelist por
# substring: se o produto casar um destes, NÃO é deletado.
_LEGIT_PATTERNS = [
    "coco ralado",
    "paçoca",
    "pacoca",
    "açúcar confeiteiro",
    "acucar confeiteiro",
    "snow sugar",
    "açúcar mascavo",
    "acucar mascavo",
    "chocolate em pó",
    "chocolate em po",
    "chocolate solúvel",
    "chocolate soluvel",
    "dr. oetker",
    "oetker",
    "cacau",
    "doce de leite",
    "creme de leite",
    "leite condensado",
    "achocolatado",
    "bala",
    "brigadeiro",
    "beijinho",
    "trufa",
]

# Delete via query builder leva os filtros .in_() na QUERY-STRING (não no
# body como o RPC) — URL tem limite prático ~8KB. Chunk de 100 UUIDs ≈ 4KB.
_DELETE_CHUNK = 100


def _is_legit(raw_product: str) -> bool:
    low = raw_product.lower()
    return any(p in low for p in _LEGIT_PATTERNS)


def _non_food_or_clause() -> str:
    """Cláusula .or_() com wildcards '*' do PostgREST (ilike).

    O PostgREST traduz '*' para '%' nos operadores embutidos (.or_/.and_) —
    convenção documentada e segura na query-string (sem ambiguidade de
    encoding de '%'). Padrões são constantes de módulo (sem input externo).
    """
    return ",".join("raw_product.ilike." + p.replace("%", "*") for p in _NON_FOOD_PATTERNS)


def _list_fps(client, limit: int = 30) -> list[dict]:
    res = (
        client.table("prices")
        .select("id,store_id,ingredient_id,raw_price,raw_product")
        .or_(_non_food_or_clause())
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def _count_fps(client) -> int:
    rows = _list_fps(client, limit=5000)
    return len([r for r in rows if not _is_legit(r.get("raw_product", ""))])


def _list_fp_ids(client, limit: int = 10000) -> list[str]:
    """Lista IDs dos FPs confirmados (não-legítimos)."""
    rows = _list_fps(client, limit=limit)
    return [r["id"] for r in rows if not _is_legit(r.get("raw_product", ""))]


def _count_by_ingredients(client, ingredient_ids: list[str]) -> int:
    if not ingredient_ids:
        return 0
    res = (
        client.table("prices")
        .select("id", count="exact")
        .in_("ingredient_id", ingredient_ids)
        .execute()
    )
    return int(res.count or 0)


def _count_total_prices(client) -> int:
    res = client.table("prices").select("id", count="exact").limit(1).execute()
    return int(res.count or 0)


def _delete_in_chunks(client, column: str, ids: list[str]) -> int:
    deleted = 0
    for i in range(0, len(ids), _DELETE_CHUNK):
        chunk = ids[i : i + _DELETE_CHUNK]
        res = client.table("prices").delete().in_(column, chunk).execute()
        deleted += len(res.data or [])
    return deleted


def _delete_by_ingredients(client, ingredient_ids: list[str]) -> int:
    if not ingredient_ids:
        return 0
    return _delete_in_chunks(client, "ingredient_id", ingredient_ids)


def _delete_fps(client) -> int:
    ids = _list_fp_ids(client)
    if not ids:
        return 0
    return _delete_in_chunks(client, "id", ids)


def _delete_test_data(client) -> int:
    return _delete_by_ingredients(client, _TEST_INGREDIENTS)


def _delete_orphans(client) -> int:
    return _delete_by_ingredients(client, _ORPHAN_INGREDIENTS)


def _validate(client) -> dict:
    """Validação pós-aplicação: confirma que FPs, test data e órfãos sumiram."""
    return {
        "fps_remaining": _count_fps(client),
        "test_data_remaining": _count_by_ingredients(client, _TEST_INGREDIENTS),
        "orphan_remaining": _count_by_ingredients(client, _ORPHAN_INGREDIENTS),
        "total_prices": _count_total_prices(client),
        "validated_at": date.today().isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="Limpeza de FPs + dados de teste em prices")
    parser.add_argument("--dry-run", action="store_true", help="Só mostra o que seria apagado")
    parser.add_argument("--execute", action="store_true", help="Aplica o DELETE")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        parser.error("Use --dry-run ou --execute")

    client = get_service_client()

    n_fps = _count_fps(client)
    n_test = _count_by_ingredients(client, _TEST_INGREDIENTS)
    n_orphan = _count_by_ingredients(client, _ORPHAN_INGREDIENTS)
    print(f"FPs (embalagem/decoração) detectados: {n_fps}")
    print(f"Dados de teste ({', '.join(_TEST_INGREDIENTS)}): {n_test}")
    print(f"Ingredientes órfãos ({', '.join(_ORPHAN_INGREDIENTS)}): {n_orphan}")

    if n_fps > 0:
        print("\nAmostra dos FPs a remover (excluindo legítimos):")
        shown = 0
        for r in _list_fps(client, limit=200):
            if not _is_legit(r.get("raw_product", "")):
                print(f"  [{r['store_id']}] {r['ingredient_id']} | R$ {r['raw_price']} | {r['raw_product'][:60]}")
                shown += 1
                if shown >= 15:
                    break
    else:
        print("\nNenhum FP encontrado com os padrões atuais.")

    if args.dry_run:
        print("\n[Dry-run] Nada foi alterado.")
        return

    deleted_fps = _delete_fps(client) if n_fps > 0 else 0
    deleted_test = _delete_test_data(client) if n_test > 0 else 0
    deleted_orphan = _delete_orphans(client) if n_orphan > 0 else 0
    print(f"\n[Executado] FPs deletados: {deleted_fps}; test data: {deleted_test}; órfãos: {deleted_orphan}")

    validation = _validate(client)
    print("\nValidação pós-aplicação:")
    print(f"  FPs restantes: {validation['fps_remaining']}")
    print(f"  Test data restantes: {validation['test_data_remaining']}")
    print(f"  Órfãos restantes: {validation['orphan_remaining']}")
    print(f"  Total de preços na tabela: {validation['total_prices']}")

    if (
        validation["fps_remaining"] == 0
        and validation["test_data_remaining"] == 0
        and validation["orphan_remaining"] == 0
    ):
        print("\n[OK] Limpeza validada — DB limpo de FPs, test data e órfãos.")
    else:
        print("\n[ATENÇÃO] Ainda restam registros — verificar manualmente.")


if __name__ == "__main__":
    main()
