import os
from scripts.validation_utils import run_cmd


def run():
    """Executes DB Deployment and Schema Validation Phase."""
    auto = os.environ.get("VALIDATION_AUTO") == "1"

    # 1. Dry run first
    print("--- DB DRY RUN ---")
    rc, stdout, stderr = run_cmd("python scripts/deploy_database.py --dry-run")
    print(stdout)
    if rc != 0 or "ERROR" in stdout:
        return False, f"DB dry-run failed: {stdout or stderr}"

    if auto:
        print("Auto mode: dry-run OK, --execute skipped.")
        return True, "DB dry-run passed (--execute skipped in auto mode)"

    confirm = input("Execute deploy_database --execute in PROD? [s/N]: ")
    if confirm.lower() != "s":
        return False, "User aborted DB deploy"

    # 2. Execute deploy
    rc, stdout, stderr = run_cmd("python scripts/deploy_database.py --execute")
    if rc != 0:
        return False, f"Deploy failed: {stdout or stderr}"

    # 3. Validate Schema (87 checks)
    rc, stdout, stderr = run_cmd("python scripts/validate_db_schema.py")
    if rc != 0:
        return False, f"Schema validation failed: {stdout or stderr}"

    return True, "DB deploy and schema validation passed"
