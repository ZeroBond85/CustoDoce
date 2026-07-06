#!/usr/bin/env python3
"""
Script para executar a restauração de um backup SQL via RPC do Supabase.
"""

import os
import sys
import base64
from supabase import create_client


def execute_rpc_restore(backup_file: str, dry_run: bool = False) -> bool:
    """Executa a restauração via RPC do Supabase."""
    if not os.path.exists(backup_file):
        print(f"Arquivo de backup não encontrado: {backup_file}", file=sys.stderr)
        return False

    # Verificar se o arquivo é válido (verificar se é um arquivo gzipped)
    try:
        with open(backup_file, 'rb') as f:
            header = f.read(2)
            if header != b'\x1f\x8b':  # Cabeçalho de um arquivo gzip
                print("Arquivo não parece ser um arquivo gzip válido.", file=sys.stderr)
                return False
    except OSError as e:
        print(f"Erro ao ler arquivo de backup: {e}", file=sys.stderr)
        return False

    # Ler o arquivo de backup
    try:
        with open(backup_file, 'rb') as f:
            backup_data = f.read()
    except OSError as e:
        print(f"Erro ao ler arquivo de backup: {e}", file=sys.stderr)
        return False

    # Configurar cliente Supabase
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

    if not supabase_url or not supabase_key:
        print("ERRO: Variáveis de ambiente SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY não configuradas.", file=sys.stderr)
        return False

    try:
        supabase = create_client(supabase_url, supabase_key)
        # Verificar se o cliente foi criado com sucesso
        if not supabase:
            print("ERRO: Cliente Supabase não foi criado corretamente.", file=sys.stderr)
            return False
    except Exception as e:
        print(f"ERRO: Falha ao criar cliente Supabase: {e}", file=sys.stderr)
        return False

    # Codificar o backup em base64
    encoded_data = base64.b64encode(backup_data).decode('utf-8')

    if dry_run:
        print(f"[DRY-RUN] Tentando executar RPC com o backup {backup_file}...")
        print("Dry-run concluído. Não foi feita nenhuma restauração real.")
        return True

    try:
        # Executar RPC para restaurar o backup
        result = supabase.rpc('restore_from_sql', data=encoded_data)
        print("Restauração via RPC concluída com sucesso!")
        print(f"Resultado: {result}")
        return True
    except Exception as e:
        print(f"Erro ao executar RPC: {e}", file=sys.stderr)
        return False


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python rpc_restore.py <backup_file> [--dry-run]")
        sys.exit(1)

    backup_file = sys.argv[1]
    dry_run = False

    for i in range(2, len(sys.argv)):
        if sys.argv[i] == '--dry-run':
            dry_run = True

    success = execute_rpc_restore(backup_file, dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()