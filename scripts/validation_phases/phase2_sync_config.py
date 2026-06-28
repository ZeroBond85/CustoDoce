from scripts.validation_utils import run_cmd


def run():
    """Executes Config Sync Phase."""
    rc, stdout, stderr = run_cmd("python scripts/sync_all_store_fields.py")
    if rc != 0:
        return False, f"Config sync failed: {stdout or stderr}"

    return True, "Config sync passed"
