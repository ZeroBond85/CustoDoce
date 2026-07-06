#!/usr/bin/env python3
"""
Script para gerenciar lock distribuído via Git Refs.

Uso:
  python scrape_lock.py acquire <run_id>
  python scrape_lock.py release <run_id>
"""

import subprocess
import sys
from datetime import datetime, timedelta

GIT_REF_PREFIX = "refs/heads/.scrape-lock-"
LOCK_EXPIRY_MINUTES = 60  # Lock expira em 1 hora


def acquire_lock(run_id: str) -> bool:
    """Cria uma ref Git temporária para lock."""
    lock_ref = f"{GIT_REF_PREFIX}{run_id}"

    # Verificar se lock já existe
    try:
        subprocess.run([
            "git", "rev-parse", lock_ref
        ], check=True, capture_output=True, text=True)
        print(f"ERRO: Lock já existe para run_id={run_id}", file=sys.stderr)
        return False
    except subprocess.CalledProcessError:
        pass

    # Criar lock
    try:
        subprocess.run([
            "git", "symbolic-ref", lock_ref, "HEAD"
        ], check=True, capture_output=True, text=True)
        print(f"Lock adquirido para run_id={run_id}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERRO: Falha ao criar lock: {e.stderr}", file=sys.stderr)
        print(f"Saída: {e.stdout}", file=sys.stderr)
        return False


def release_lock(run_id: str) -> bool:
    """Remove a ref Git de lock."""
    lock_ref = f"{GIT_REF_PREFIX}{run_id}"

    try:
        subprocess.run([
            "git", "update-ref", "-d", lock_ref
        ], check=True, capture_output=True, text=True)
        print(f"Lock liberado para run_id={run_id}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERRO: Falha ao liberar lock: {e.stderr}", file=sys.stderr)
        return False


def check_lock_expiry(run_id: str) -> bool:
    """Verifica se o lock está expirado."""
    lock_ref = f"{GIT_REF_PREFIX}{run_id}"

    try:
        # Obter o timestamp do commit da ref
        result = subprocess.run([
            "git", "show", f"{lock_ref}^0", "--format=%ct"
        ], check=True, capture_output=True, text=True)
        commit_timestamp = int(result.stdout.strip())

        # Verificar se o lock está expirado
        if datetime.fromtimestamp(commit_timestamp) < datetime.now() - timedelta(minutes=LOCK_EXPIRY_MINUTES):
            print(f"Lock expirado para run_id={run_id}")
            return True
        return False
    except subprocess.CalledProcessError:
        print(f"ERRO: Lock não encontrado ou inválido para run_id={run_id}", file=sys.stderr)
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python scrape_lock.py [acquire|release] <run_id>")
        sys.exit(1)

    action = sys.argv[1]
    run_id = sys.argv[2]

    if action == "acquire":
        success = acquire_lock(run_id)
    elif action == "release":
        success = release_lock(run_id)
    else:
        print(f"Ação inválida: {action}")
        sys.exit(1)

    sys.exit(0 if success else 1)