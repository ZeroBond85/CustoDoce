import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.validation_utils import notify_telegram, log_event

# Import phases
from scripts.validation_phases import (
    phase0_static,
    phase1_deploy_db,
    phase2_sync_config,
    phase3_collect,
    phase4_report,
    phase5_tests,
    phase6_health,
)


def _has_real_env() -> bool:
    """True when project .env with real Supabase/email/Telegram credentials exists."""
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(env_path):
        return False
    with open(env_path, encoding="utf-8") as f:
        content = f.read()
    required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]
    return all(f"{k}=" in content and f"{k}=\n" not in content for k in required)


# Production-ready phases require real Supabase + external services.
LOCAL_PHASES = [
    ("Static Analysis", phase0_static),
    ("Comprehensive Tests", phase5_tests),
]

PROD_PHASES = [
    ("Static Analysis", phase0_static),
    ("DB Deploy & Schema", phase1_deploy_db),
    ("Config Sync", phase2_sync_config),
    ("Full Collection", phase3_collect),
    ("Daily Report", phase4_report),
    ("Comprehensive Tests", phase5_tests),
    ("Final Health Check", phase6_health),
]


def main():
    print("=" * 60)
    print(" CUSTODOCE FULL PRODUCTION VALIDATION LOOP")
    print("=" * 60)

    # In local-only mode (no .env or test env) only run safe phases
    has_real_env = _has_real_env()
    force_full = "--full" in sys.argv
    if force_full and not has_real_env:
        print("\nERROR: --full mode requires a .env with SUPABASE_URL/KEY, TELEGRAM_TOKEN, etc.")
        sys.exit(1)

    if has_real_env or force_full:
        phases = PROD_PHASES
        mode_label = "FULL PRODUCTION"
    else:
        phases = LOCAL_PHASES
        mode_label = "LOCAL (no real .env detected → skipping network-dependent phases)"
    print(f"\n Mode: {mode_label}")
    print(f" Phases: {[p[0] for p in phases]}")

    # Mark auto mode so phases skip interactive prompts (EOFError-proof)
    os.environ["VALIDATION_AUTO"] = "1"
    if phases is PROD_PHASES:
        backup_exists = any(f.startswith("backup_prod_") and f.endswith(".sql") for f in os.listdir("."))
        if not backup_exists:
            print("\nERROR: No production backup found in current directory!")
            print("Please run: pg_dump ... > backup_prod_$(date +%F).sql")
            sys.exit(1)

    print("\n--- Running all phases (single pass) ---")
    all_passed = True
    failures = []

    for name, module in phases:
        print(f"Running {name}...", end=" ", flush=True)
        notify_telegram(f"Starting {name}...")

        success, message = module.run()

        if success:
            print("PASSED")
            log_event({"phase": name, "status": "success", "message": message})
        else:
            print("FAILED")
            print(f"\nFAILURE in {name}: {message}")
            failures.append((name, message))
            all_passed = False
            log_event({"phase": name, "status": "failure", "message": message})

    if all_passed:
        print("\n" + "=" * 60)
        print("CONGRATULATIONS! All production phases passed!")
        print("=" * 60)
        notify_telegram("ALL PRODUCTION PHASES PASSED! System is 100% Healthy.")
    else:
        print("\n" + "=" * 60)
        print(f"VALIDATION FAILED - {len(failures)} phase(s) failed:")
        for name, msg in failures:
            print(f"  ❌ {name}: {msg}")
        print("=" * 60)
        notify_telegram(f"Validation FAILED: {len(failures)} phase(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
