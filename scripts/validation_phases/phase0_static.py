import os

from scripts.validation_utils import open_editor_at, run_cmd


def run():
    """Executes Static Analysis Phase."""
    cmds = [
        ("Ruff Lint", "python -m ruff check . --fix --unsafe-fixes --output-format=concise"),
        ("Mypy Type Check", "python -m mypy . --show-error-codes"),
        ("Ruff Format", "python -m ruff format --check ."),
    ]

    for name, cmd in cmds:
        rc, stdout, stderr = run_cmd(cmd)
        if rc != 0:
            if name == "Ruff Format" and os.environ.get("VALIDATION_AUTO") == "1":
                run_cmd("python -m ruff format .")
                rc, stdout, stderr = run_cmd(cmd)
                if rc == 0:
                    continue
            if os.environ.get("VALIDATION_AUTO") != "1":
                import re

                match = re.search(r"([a-zA-Z0-9._/\\\- ]+):(\d+):", stdout + stderr)
                if match:
                    file, line = match.groups()
                    open_editor_at(file, int(line))

            return False, f"{name} failed: {stdout or stderr}"

    return True, "Static checks passed"
