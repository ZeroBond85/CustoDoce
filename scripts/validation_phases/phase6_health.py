from scripts.validation_utils import run_cmd


def run():
    """Executes Final Health Check Phase (against PROD)."""
    # We use the staging validator but point it to PROD (it uses .env)
    rc, stdout, stderr = run_cmd("python scripts/validate_staging.py")
    if rc != 0:
        return False, f"Health check failed: {stdout or stderr}"

    return True, "Final health check passed"
