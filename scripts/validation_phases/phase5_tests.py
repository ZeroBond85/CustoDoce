from scripts.validation_utils import run_cmd, open_editor_at
import re


def run():
    """Executes Comprehensive Test Suite Phase."""
    # Run unit, schema and integration tests
    cmd = "python -m pytest tests/unit/ tests/schema/ tests/integration/ -q --tb=short -x"
    rc, stdout, stderr = run_cmd(cmd)

    if rc != 0:
        # Try to find the failing test and line
        match = re.search(r"([a-zA-Z0-9._/\\\- ]+):(\d+)", stdout + stderr)
        if match:
            file, line = match.groups()
            open_editor_at(file, int(line))

        return False, f"Test suite failed: {stdout or stderr}"

    return True, "All tests passed"
