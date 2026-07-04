"""Time budget guard for CI jobs.

Usage:
  python scripts/check_time_budget.py --timeout-minutes 10 --label "unit"

Checks if elapsed time since CI_JOB_START exceeds 70% of timeout-minutes.
Prints ::warning:: annotation in GitHub Actions if exceeded.
Exit code 0 (non-blocking).
"""

import argparse
import os
import time

THRESHOLD_RATIO = 0.70  # 30% margin


def main():
    parser = argparse.ArgumentParser(description="CI time budget guard")
    parser.add_argument("--timeout-minutes", type=int, required=True, help="Job timeout in minutes")
    parser.add_argument("--label", type=str, default="job", help="Job label for warnings")
    args = parser.parse_args()

    start_epoch = os.environ.get("CI_JOB_START")
    if not start_epoch:
        print(f"[TIMEBUDGET] CI_JOB_START not set — skipping check for '{args.label}'")
        return

    try:
        start = int(start_epoch)
    except ValueError:
        print(f"[TIMEBUDGET] Invalid CI_JOB_START={start_epoch} for '{args.label}'")
        return

    elapsed = time.time() - start
    timeout_sec = args.timeout_minutes * 60
    threshold_sec = timeout_sec * THRESHOLD_RATIO

    pct = (elapsed / timeout_sec) * 100

    if elapsed > threshold_sec:
        msg = (
            f"[TIMEBUDGET] ⚠ '{args.label}' used {elapsed:.0f}s / {timeout_sec}s "
            f"({pct:.0f}% of timeout). Exceeds {THRESHOLD_RATIO * 100:.0f}% threshold "
            f"({threshold_sec:.0f}s). Consider reducing test scope or increasing timeout."
        )
        print(f"::warning ::{msg}")
    else:
        print(f"[TIMEBUDGET] ✓ '{args.label}' {elapsed:.0f}s / {timeout_sec}s ({pct:.0f}%) — within budget")


if __name__ == "__main__":
    main()
