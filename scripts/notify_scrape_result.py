#!/usr/bin/env python3
"""
Script para notificar o resultado do scraping.
"""

import os
import subprocess
import sys


def send_telegram_message(message: str) -> bool:
    """Envia mensagem para o Telegram Bot."""
    if not os.getenv('TELEGRAM_BOT_TOKEN') or not os.getenv('TELEGRAM_CHAT_ID'):
        print("ERRO: Variáveis de ambiente TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configuradas.", file=sys.stderr)
        return False

    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        result = subprocess.run([
            "curl", "-s", "-X", "POST", url,
            "-H", "Content-Type: application/json",
            "-d", str(payload)
        ], capture_output=True, text=True, check=True)
        print("Mensagem enviada para Telegram.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERRO: Falha ao enviar mensagem para Telegram: {e.stderr}", file=sys.stderr)
        print(f"Detalhes: {e.stdout}", file=sys.stderr)
        return False


def notify_scrape_result(mode: str, status: str) -> bool:
    """Notifica o resultado do scraping."""
    if status == 'success':
        message = f"""
*Scrape {mode} concluído com sucesso!*"

*Status:* Sucesso
"""
    elif status == 'failure':
        message = f"""
*Scrape {mode} falhou!*"

*Status:* Falha
"""
    else:
        message = f"""
*Scrape {mode} com status: {status}*"
"""

    return send_telegram_message(message)


def main() -> None:
    if len(sys.argv) < 3:
        print("Uso: python notify_scrape_result.py <mode> <status>")
        sys.exit(1)

    mode = sys.argv[1]
    status = sys.argv[2]

    success = notify_scrape_result(mode, status)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()