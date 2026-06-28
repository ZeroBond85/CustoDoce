import os
from scripts.validation_utils import run_cmd


def run():
    """Executes Daily Report Phase."""
    if os.environ.get("VALIDATION_AUTO") == "1":
        os.environ["SKIP_SEND"] = "1"

    rc, stdout, stderr = run_cmd("python scripts/send_daily_report.py")
    if rc != 0:
        return False, f"Daily report failed: {stdout or stderr}"

    return True, "Daily report passed"
