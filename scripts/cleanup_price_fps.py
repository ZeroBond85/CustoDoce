"""Limpeza de Falsos Positivos (FPs) + dados de teste na tabela `prices`.

Segue AGENTS.md regra #18 (fluxo correto): path RPC `exec_sql`/`exec_sql_query`
(porta 443), dry-run antes, validação pós-aplicação.

Uso:
    python scripts/cleanup_price_fps.py --dry-run    # só mostra o que seria apagado
    python scripts/cleanup_price_fps.py --execute    # aplica o DELETE
"""

# ruff: noqa: S608  # SQL construído com valores de whitelist/IDs locais (safe)

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

# Lojas onde os FPs foram confirmados nos logs (RIZZO/casa_santa_luzia)
_TARGET_STORES = ["rizzo_confeitaria", "casa_santa_luzia"]

# Ingredientes de teste que não devem existir em produção
_TEST_INGREDIENTS = ["_test_hist_unique_ing"]

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


def _is_legit(raw_product: str) -> bool:
    low = raw_product.lower()
    return any(p in low for p in _LEGIT_PATTERNS)


def _build_where(target_stores: list[str] | None = None) -> str:
    conditions = []
    if target_stores:
        quoted = ",".join(f"'{s}'" for s in target_stores)
        conditions.append(f"store_id IN ({quoted})")
    tok_conds = " OR ".join(f"raw_product ILIKE '{t}'" for t in _NON_FOOD_PATTERNS)
    conditions.append(f"({tok_conds})")
    return " AND ".join(conditions)


def _count_fps(client, dry_run: bool) -> int:
    rows = _list_fps(client, limit=5000)
    return len([r for r in rows if not _is_legit(r.get("raw_product", ""))])


def _list_fps(client, limit: int = 30) -> list[dict]:
    sql = (
        f"SELECT id, store_id, ingredient_id, raw_price, raw_product "
        f"FROM prices WHERE {_build_where()} ORDER BY created_at DESC LIMIT {limit}"
    )
    res = client.rpc("exec_sql_query", {"sql": sql}).execute()
    return res.data or []


def _list_fp_ids(client, limit: int = 10000) -> list[str]:
    """Lista IDs dos FPs confirmados (não-legítimos)."""
    rows = _list_fps(client, limit=limit)
    return [r["id"] for r in rows if not _is_legit(r.get("raw_product", ""))]


def _count_test_data(client) -> int:
    quoted = ",".join(f"'{i}'" for i in _TEST_INGREDIENTS)
    sql = f"SELECT COUNT(*) AS n FROM prices WHERE ingredient_id IN ({quoted})"
    res = client.rpc("exec_sql_query", {"sql": sql}).execute()
    data = res.data
    if isinstance(data, list) and data:
        return int(data[0].get("n", 0))
    if isinstance(data, dict):
        return int(data.get("n", 0))
    return 0


def _delete_fps(client) -> int:
    ids = _list_fp_ids(client)
    if not ids:
        return 0
    # Deleta em lotes de 500 (limite de IN)
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        quoted = ",".join(f"'{x}'" for x in chunk)
        sql = f"DELETE FROM prices WHERE id IN ({quoted})"
        client.rpc("exec_sql", {"sql": sql}).execute()
    return len(ids)


def _delete_test_data(client) -> int:
    quoted = ",".join(f"'{i}'" for i in _TEST_INGREDIENTS)
    sql = f"DELETE FROM prices WHERE ingredient_id IN ({quoted})"
    client.rpc("exec_sql", {"sql": sql}).execute()
    # Ingredientes de teste podem ter N linhas; contamos via validação pós.
    return len(_TEST_INGREDIENTS)


def _validate(client) -> dict:
    """Validação pós-aplicação: confirma que FPs e test data sumiram."""
    fps_left = _count_fps(client, dry_run=True)
    test_left = _count_test_data(client)
    total = client.rpc(
        "exec_sql_query", {"sql": "SELECT COUNT(*) AS n FROM prices"}
    ).execute()
    total_n = 0
    data = total.data
    if isinstance(data, list) and data:
        total_n = int(data[0].get("n", 0))
    elif isinstance(data, dict):
        total_n = int(data.get("n", 0))
    return {
        "fps_remaining": fps_left,
        "test_data_remaining": test_left,
        "total_prices": total_n,
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

    n_fps = _count_fps(client, dry_run=args.dry_run)
    n_test = _count_test_data(client)
    print(f"FPs (embalagem/decoração) detectados: {n_fps}")
    print(f"Dados de teste (_test_hist_unique_ing): {n_test}")

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
    print(f"\n[Executado] FPs deletados: {deleted_fps}; test data deletados: {deleted_test}")

    validation = _validate(client)
    print("\nValidação pós-aplicação:")
    print(f"  FPs restantes: {validation['fps_remaining']}")
    print(f"  Test data restantes: {validation['test_data_remaining']}")
    print(f"  Total de preços na tabela: {validation['total_prices']}")

    if validation["fps_remaining"] == 0 and validation["test_data_remaining"] == 0:
        print("\n[OK] Limpeza validada — DB limpo de FPs e test data.")
    else:
        print("\n[ATENÇÃO] Ainda restam registros — verificar manualmente.")


if __name__ == "__main__":
    main()