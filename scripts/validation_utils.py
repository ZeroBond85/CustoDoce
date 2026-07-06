import json
import os
import subprocess

from services.logger import logger


def run_cmd(cmd: str, timeout: int = 3600, cwd: str = None) -> tuple[int, str, str]:
    """Executes a command and returns returncode, stdout, stderr."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd)  # noqa: S602
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
    cmd = f"code -g {file_path}:{line}"
    subprocess.run(cmd, shell=True)  # noqa: S602


def log_event(event: dict):
    """Logs validation event to a JSONL file."""
    log_dir = "data"
    os.makedirs(log_dir, exist_ok=True)
    # In a real implementation, the filename would be passed or stored globally
    # For now, we just print to console and could append to a file
    print(json.dumps(event))


def get_env_var(var: str, default: str = None) -> str:
    return os.environ.get(var, default)
