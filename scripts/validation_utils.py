import json
import os
import shlex
import subprocess

from services.logger import logger


def _tokenize(cmd: str) -> list[str]:
    """Splita comando respeitando aspas, preservando backslashes (paths Windows)."""
    return [tok.strip('"') for tok in shlex.split(cmd, posix=False)]


def run_cmd(cmd: str, timeout: int = 3600, cwd: str = None) -> tuple[int, str, str]:
    """Executes a command and returns returncode, stdout, stderr."""
    try:
        result = subprocess.run(
            _tokenize(cmd), capture_output=True, text=True, timeout=timeout, cwd=cwd, check=False
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as e:
        return 124, e.stdout.decode() if e.stdout else "", e.stderr.decode() if e.stderr else "Timeout expired"

    except Exception as e:
        return 1, "", str(e)


def notify_telegram(message: str):
    """Sends a notification to the Telegram bot."""
    try:
        from dotenv import load_dotenv

        from services.telegram_service import send_telegram_message

        load_dotenv()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if chat_id:
            send_telegram_message(chat_id, message)
    except Exception as e:
        logger.error("Failed to send telegram notification: %s", e)


def open_editor_at(file_path: str, line: int):
    """Opens the editor at a specific line (default: VS Code)."""
    if not os.path.exists(file_path):
        print(f"File {file_path} not found.")
        return

    # VS Code: code -g file:line
    subprocess.run(["code", "-g", f"{file_path}:{line}"], check=False)


def log_event(event: dict):
    """Logs validation event to a JSONL file."""
    log_dir = "data"
    os.makedirs(log_dir, exist_ok=True)
    # In a real implementation, the filename would be passed or stored globally
    # For now, we just print to console and could append to a file
    print(json.dumps(event))


def get_env_var(var: str, default: str = None) -> str:
    return os.environ.get(var, default)
