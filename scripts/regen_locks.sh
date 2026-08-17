#!/usr/bin/env bash
# regen_locks.sh — Regenera TODOS os lock files de forma canonica.
#
# Fonte unica de verdade. NUNCA rode pip-compile manualmente com comando
# diferente deste — o requirements-test.lock DEVE ser o combined
# (test + dev + prod), caso contrario o CI perde deps de producao e quebra
# com ModuleNotFoundError / drift de badge no docs-sync.
#
# IMPORTANTE (AGENTS regra #10): rode SEMPRE em WSL/Linux (Python 3.14.6),
# NUNCA no Windows — senao resolve pacotes condicionais de plataforma
# (colorama/tzdata) que nao existem no Linux e geram drift silencioso.
#
# Uso:
#   bash scripts/regen_locks.sh
set -euo pipefail

cd "$(dirname "$0")/.."

export PIP_EXTRA_INDEX_URL="https://download.pytorch.org/whl/cpu"
export PIP_NO_WARN_YANKED=1

PIP_COMPILE="python -m piptools compile --allow-unsafe --no-strip-extras"

echo "==> prod.lock (requirements-prod.in)"
$PIP_COMPILE --output-file=requirements-prod.lock requirements-prod.in

echo "==> dev.lock (requirements-dev.in + requirements-prod.in)"
$PIP_COMPILE --output-file=requirements-dev.lock requirements-dev.in requirements-prod.in

echo "==> test.lock (requirements-test.in + requirements-dev.in + requirements-prod.in)"
$PIP_COMPILE --output-file=requirements-test.lock requirements-test.in requirements-dev.in requirements-prod.in

echo "==> requirements.lock = requirements-test.lock (copia canonica)"
cp requirements-test.lock requirements.lock

echo "==> OK. Lock files regenerados. Faca commit de TODOS os 4 arquivos."
