#!/usr/bin/env python3
"""
Script para testar o lock distribuído.
"""

import subprocess
import sys
import time


def test_lock_acquisition(run_id: str) -> bool:
    """Testa a aquisição e liberação do lock."""

    # Tentar adquirir o lock
    print(f"Tentando adquirir lock para run_id={run_id}")
    result = subprocess.run([
        "python", "scrape_lock.py", "acquire", run_id
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Falha ao adquirir lock: {result.stderr}")
        return False

    print(f"Lock adquirido com sucesso para run_id={run_id}")

    # Verificar se o lock foi criado
    lock_ref = f"refs/heads/.scrape-lock-{run_id}"
    try:
        subprocess.run(["git", "rev-parse", lock_ref], check=True, capture_output=True)
        print(f"Lock verificado com sucesso: {lock_ref}")
    except subprocess.CalledProcessError:
        print(f"Erro ao verificar lock: {lock_ref} não encontrado")
        return False

    # Liberar o lock
    print(f"Liberando lock para run_id={run_id}")
    result = subprocess.run([
        "python", "scrape_lock.py", "release", run_id
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Falha ao liberar lock: {result.stderr}")
        return False

    print(f"Lock liberado com sucesso para run_id={run_id}")
    return True


def test_lock_concurrency(run_id1: str, run_id2: str) -> bool:
    """Testa a concorrência do lock."""

    # Tentar adquirir o lock simultaneamente
    print(f"Tentando adquirir locks simultaneamente para run_id={run_id1} e {run_id2}")

    # Processo 1
    process1 = subprocess.Popen([
        "python", "scrape_lock.py", "acquire", run_id1
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Processo 2
    process2 = subprocess.Popen([
        "python", "scrape_lock.py", "acquire", run_id2
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Aguardar um pouco para verificar se ambos tentam adquirir o lock
    time.sleep(1)

    # Verificar saída dos processos
    stdout1, stderr1 = process1.communicate()
    stdout2, stderr2 = process2.communicate()

    if process1.returncode == 0 and process2.returncode == 0:
        print("Ambos os locks foram adquiridos simultaneamente, o que não deve ocorrer.")
        return False

    if process1.returncode != 0 or process2.returncode != 0:
        print(f"Um dos locks falhou: {stderr1} ou {stderr2}")
        return True  # Esperado que um falhe

    print("Teste de concorrência concluído com sucesso.")
    return True


def main() -> None:
    run_id1 = "test_lock_1"
    run_id2 = "test_lock_2"

    # Testar aquisição e liberação de lock
    print("=== Testando aquisição e liberação de lock ===")
    success1 = test_lock_acquisition(run_id1)

    if not success1:
        print("Teste de aquisição e liberação de lock falhou.")
        sys.exit(1)

    # Testar concorrência de lock
    print("\n=== Testando concorrência de lock ===")
    success2 = test_lock_concurrency(run_id1, run_id2)

    if not success2:
        print("Teste de concorrência de lock falhou.")
        sys.exit(1)

    print("\nTodos os testes de lock foram concluídos com sucesso.")
    sys.exit(0)


if __name__ == "__main__":
    main()