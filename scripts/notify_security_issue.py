#!/usr/bin/env python3
"""
Script para notificar falhas de segurança (CVEs) em PRs.

Uso:
  python notify_security_issue.py <cve_severity> <cve_description> <pr_number>
"""

import json
import os
import subprocess
import sys

# Configurações
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


def send_telegram_message(message: str) -> bool:
    """Envia mensagem para o Telegram Bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERRO: Variáveis de ambiente TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configuradas.", file=sys.stderr)
        return False

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERRO: Variáveis de ambiente TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configuradas.", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = subprocess.check_output(
            ["curl", "-s", "-X", "POST", url, "-d", json.dumps(payload)],
            stderr=subprocess.STDOUT,
            text=True,
        )
        print("Mensagem enviada para Telegram.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERRO: Falha ao enviar mensagem para Telegram: {e.output}", file=sys.stderr)
        return False


def send_github_comment(pr_number: int, message: str) -> bool:
    """Adiciona comentário no PR no GitHub."""
    if not GITHUB_TOKEN:
        print("ERRO: Variável de ambiente GITHUB_TOKEN não configurada.", file=sys.stderr)
        return False

    repo = os.getenv("GITHUB_REPOSITORY")
    if not repo:
        print("ERRO: Variável de ambiente GITHUB_REPOSITORY não configurada.", file=sys.stderr)
        return False

    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    payload = {
        "body": message
    }

    try:
        response = subprocess.check_output(
            ["curl", "-s", "-X", "POST", url,
             "-H", f"Authorization: token {GITHUB_TOKEN}",
             "-H", "Accept: application/vnd.github.v3+json",
             "-d", json.dumps(payload)],
            stderr=subprocess.STDOUT,
            text=True,
        )
        print("Comentário adicionado no PR.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERRO: Falha ao adicionar comentário no PR: {e.output}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERRO inesperado ao adicionar comentário no PR: {e}", file=sys.stderr)
        return False


def notify_security_issue(severity: str, description: str, pr_number: int) -> bool:
    """Notifica falha de segurança via Telegram e GitHub."""
    message = f"""
*Alerta de Segurança*

**Severidade:** {severity}
**Descrição:** {description}
**PR:** #{pr_number}

*Este PR contém uma vulnerabilidade crítica e deve ser revisado imediatamente.*
"""

    # Enviar mensagem para Telegram
    telegram_success = send_telegram_message(message)

    # Adicionar comentário no PR (apenas se for PR real, não #0)
    if pr_number is not None and pr_number > 0:
        comment_message = f"""
Este PR contém uma vulnerabilidade de segurança classificada como **{severity}**.

**Descrição:** {description}

Por favor, revise e corrija antes de mergear.
"""
        github_success = send_github_comment(pr_number, comment_message)
        return telegram_success and github_success

    # Só precisa do Telegram se não for PR
    return telegram_success


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Uso: python notify_security_issue.py <severity> <description> <pr_number>")
        sys.exit(1)

    severity = sys.argv[1]
    description = sys.argv[2]
    pr_number = int(sys.argv[3])

    success = notify_security_issue(severity, description, pr_number)
    sys.exit(0 if success else 1)