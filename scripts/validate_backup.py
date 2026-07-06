#!/usr/bin/env python3
"""
Script para validar a restauração de um backup SQL.
"""

import os
import subprocess
import sys


def validate_backup(backup_file: str, sha256_file: str | None = None) -> bool:
    """Valida a integridade do arquivo de backup."""
    if not os.path.exists(backup_file):
        print(f"Arquivo de backup não encontrado: {backup_file}", file=sys.stderr)
        return False

    # Verificar checksum SHA256
    if sha256_file and os.path.exists(sha256_file):
        try:
            with open(sha256_file, 'r') as f:
                expected_sha256 = f.read().strip().split()[0]

            with open(backup_file, 'rb') as f:
                actual_sha256 = subprocess.check_output(['sha256sum', backup_file], text=True).strip().split()[0]

            if expected_sha256 != actual_sha256:
                print(f"Checksum SHA256 não corresponde: esperado {expected_sha256}, obtido {actual_sha256}", file=sys.stderr)
                return False
        except subprocess.CalledProcessError as e:
            print(f"Erro ao calcular checksum: {e}", file=sys.stderr)
            return False

    # Verificar se o arquivo é válido
    try:
        subprocess.check_output(['gzip', '-t', backup_file], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print(f"Arquivo de backup inválido: {e.output.decode()}", file=sys.stderr)
        return False

    # Verificar se é um dump SQL válido
    try:
        result = subprocess.check_output(['pg_restore', '--list', backup_file], stderr=subprocess.STDOUT, text=True)
        print(f"Dump SQL válido. Tabelas encontradas:\n{result}")
    except subprocess.CalledProcessError as e:
        print(f"Arquivo não é um dump SQL válido: {e.output.decode()}", file=sys.stderr)
        return False

    return True


def dry_run_restore(backup_file: str) -> bool:
    """Realiza um dry-run da restauração."""
    try:
        subprocess.check_output(['pg_restore', '--list', backup_file], stderr=subprocess.STDOUT)
        print(f"Dry-run de restauração concluído com sucesso para {backup_file}.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Erro durante dry-run: {e.output.decode()}", file=sys.stderr)
        return False


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python validate_backup.py <backup_file> [--sha256 <sha256_file>] [--dry-run]")
        sys.exit(1)

    backup_file = sys.argv[1]
    sha256_file = None
    dry_run = False

    for i in range(2, len(sys.argv)):
        if sys.argv[i] == '--sha256' and i + 1 < len(sys.argv):
            sha256_file = sys.argv[i + 1]
            i += 1
        elif sys.argv[i] == '--dry-run':
            dry_run = True

    success = dry_run_restore(backup_file) if dry_run else validate_backup(backup_file, sha256_file)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()