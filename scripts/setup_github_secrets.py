#!/usr/bin/env python3
"""Script para configurar secrets do GitHub Actions via gh CLI.

Uso:
    python scripts/setup_github_secrets.py

Os secrets sao lidos do arquivo .env na raiz do projeto.
"""

import os
import subprocess
import sys


def run_gh_secret_set(name, value):
    """Define um secret no GitHub via gh CLI."""
    cmd = ["gh", "secret", "set", name]
    proc = subprocess.run(
        cmd,
        input=value.encode(),
        capture_output=True,
    )
    if proc.returncode == 0:
        print(f"  OK  {name}")
    else:
        print(f"  ERR {name}: {proc.stderr.decode().strip()}")
    return proc.returncode == 0


def load_env(path=".env"):
    """Lê arquivo .env e retorna dict de variáveis."""
    env = {}
    if not os.path.exists(path):
        print(f"ERRO: Arquivo {path} não encontrado")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def main():
    env = load_env()

    # Mapeamento: nome do secret -> chave no .env
    secrets_map = {
        "SUPABASE_URL": "SUPABASE_URL",
        "SUPABASE_ANON_KEY": "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY": "SUPABASE_SERVICE_ROLE_KEY",
        "AUTH_SECRET_KEY": "AUTH_SECRET_KEY",
        "ADMIN_PASSWORD": "ADMIN_PASSWORD",
        "TELEGRAM_TOKEN": "TELEGRAM_TOKEN",
        "TELEGRAM_CHAT_ID": "TELEGRAM_CHAT_ID",
        "SMTP_HOST": "SMTP_HOST",
        "SMTP_PORT": "SMTP_PORT",
        "SMTP_USER": "SMTP_USER",
        "SMTP_PASSWORD": "SMTP_PASSWORD",
        "SMTP_FROM": "SMTP_FROM",
        "GMAIL_USER": "GMAIL_USER",
        "GMAIL_APP_PASSWORD": "GMAIL_APP_PASSWORD",
        "ALERT_EMAIL_TO": "ALERT_EMAIL_TO",
        "GH_PAT": "GH_PAT",
    }

    print("\nConfigurando secrets no GitHub Actions...\n")
    success = 0
    skipped = 0
    errors = 0

    for secret_name, env_key in secrets_map.items():
        value = env.get(env_key, "")
        if not value:
            print(f"  SKIP {secret_name} (vazio no .env)")
            skipped += 1
            continue
        if run_gh_secret_set(secret_name, value):
            success += 1
        else:
            errors += 1

    print(f"\nResumo: {success} configurados, {skipped} pulados, {errors} erros")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
