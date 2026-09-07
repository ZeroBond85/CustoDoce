#!/usr/bin/env python3
"""FASE B1 — Auto-aprovação da review_queue por confiança (agendável).

Orquestra services.review_queue_service.auto_approve_high_confidence em CLI
para rodar via cron (GitHub Actions) ou dashboard.

Nota (calibração A0.5/A1): como o gate de persistência é 0.82 e o
review_threshold agora é 0.78, a review_queue só contém combined em
[0.78, 0.82). Aprovação automática cega por threshold (>= 0.80) reintroduz
falsos positivos semânticos (leite UHT -> leite em pó, cobertura -> leite
em pó). Por padrão este script exige CONFIRMAÇÃO DO LLM (--llm-confirmed):
só aprova o candidato top-1 se o LLM responder match com conf >= floor.

Modos:
  --dry-run       (default)  apenas relata vereditos (não escreve)
  --execute       aprova de fato (resolves loja, upsert price, marc. approved)
  --threshold X   banda inferior de confidence na fila (default 0.78)
  --limit N       max de itens a avaliar (default: sem limite)
  --llm-confirmed usa LLM classifier para confirmar o candidato top-1 (default)
  --no-llm        aprova cego por threshold (NÃO recomendado — reintroduz FPs)
  --llm-floor X   piso de confidence do LLM para aprovar (default 0.85)

Exit codes:
  0  sucesso (dry-run ou execute sem falhas)
  1  falha no upsert/resolução (loja/ingrediente)
  2  llm_confirmed com itens sem veredito (rate-limit) — ficaram p/ revisão humana
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.review_queue_service import (  # noqa: E402
    auto_approve_high_confidence,
    auto_approve_llm_confirmed,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Executa a aprovação (default: dry-run)")
    parser.add_argument("--threshold", type=float, default=0.78, help="Confiança mínima (default 0.78)")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de itens avaliados")
    parser.add_argument("--llm-confirmed", dest="llm_confirmed", action="store_true", default=True)
    parser.add_argument("--no-llm", dest="llm_confirmed", action="store_false", help="Aprova cego por threshold")
    parser.add_argument("--llm-floor", type=float, default=0.85, help="Piso de confidence do LLM (default 0.85)")
    args = parser.parse_args()

    if args.llm_confirmed:
        stats = auto_approve_llm_confirmed(
            threshold=args.threshold,
            limit=args.limit,
            dry_run=not args.execute,
            llm_floor=args.llm_floor,
        )
    else:
        stats = auto_approve_high_confidence(
            threshold=args.threshold,
            limit=args.limit,
            dry_run=not args.execute,
        )
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    if not args.execute:
        print("(dry-run: nenhum dado foi alterado. Use --execute para aprovar.)")
        return 0

    if stats.get("failed", 0) > 0:
        print(f"AVISO: {stats['failed']} falhas (loja/ingrediente não resolvidos ou upsert falhou).", file=sys.stderr)
        return 1

    if args.llm_confirmed and stats.get("llm_failures", 0) > 0:
        print(
            f"ALERTA: {stats['llm_failures']} itens sem veredito LLM "
            "(provável rate-limit/circuit — ficaram para revisão humana).",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())