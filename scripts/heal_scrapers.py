"""
scripts/heal_scrapers.py

CLI for self-healing scraper lifecycle management.

Subcommands
-----------
  run-all                 Audit + reactivate every disabled scraper (idempotent).
  test-store NAME         Heal exactly one scraper (used for manual triage).
  list-disabled           Print all currently-disabled scrapers.
  failures NAME [DAYS]    Show recent failure events from scraper_health_log.
  dry-run                 Same as `run-all` but does not mutate DB.

All commands read SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY from .env.

This script is invoked by:
  * Manual:  python scripts/heal_scrapers.py run-all
  * Manual:  python scripts/heal_scrapers.py test-store "Cacau Center"
  * CI cron: .github/workflows/heal-scrapers.yml (every 15 days).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, UTC

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.supabase_client import get_service_client  # noqa: E402
from services.scraper_health import (  # noqa: E402
    attempt_heal,
)


def _utc_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def list_disabled() -> int:
    """Show every store with is_active=False."""
    client = get_service_client()
    res = (
        client.table("stores").select("id, name, tier, is_active, type").eq("is_active", False).order("name").execute()
    )
    rows = res.data or []
    if not rows:
        print("  (none — all stores are active)")
        return 0
    print(f"Disabled stores: {len(rows)}")
    for s in rows:
        print(
            f"  - id={s['id'][:8] if s.get('id') else '-'} name={s['name']!r} tier={s.get('tier')} type={s.get('type')}"
        )
    return len(rows)


def test_store(name: str, dry_run: bool = False) -> dict:
    """Run attempt_heal() scoped to a single scraper name."""
    summary = attempt_heal(scraper_name=name, dry_run=dry_run)
    print(f"[test-store] {name} dry_run={dry_run}: {json.dumps(summary, indent=2)}")
    return summary


def failures(name: str, days: int = 30) -> int:
    """Show scraper_health_log events for a scraper in the last N days."""
    client = get_service_client()
    cutoff = _utc_iso(datetime.now(tz=UTC) - timedelta(days=days))
    res = (
        client.table("scraper_health_log")
        .select("created_at, event_type, error_class, reason, failures_count, is_active, attempted_by")
        .eq("scraper_name", name)
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )
    rows = res.data or []
    print(f"Scraper {name!r} events in last {days} days: {len(rows)}")
    if not rows:
        return 0
    counts_by_type: dict[str, int] = defaultdict(int)
    for r in rows:
        counts_by_type[r.get("event_type", "unknown")] += 1
        ts = r.get("created_at", "")[:19]
        print(
            f"  - {ts} type={r.get('event_type')} "
            f"class={r.get('error_class') or '-'} "
            f"failures={r.get('failures_count')} active={r.get('is_active')} "
            f"by={r.get('attempted_by')}"
        )
        snippet = (r.get("reason") or "")[:80]
        if snippet:
            print(f'      reason: "{snippet}{"..." if len(snippet) >= 80 else ""}"')
    print("Totals:", dict(counts_by_type))
    return len(rows)


def run_all(dry_run: bool = False, threshold_days: int | None = None) -> dict:
    """Audit + (re-)activate every currently-disabled scraper.

    Returns the summary from services.scraper_health.attempt_heal().
    """
    if threshold_days is not None:
        os.environ["SCRAPER_HEALTH_HEAL_DAYS"] = str(threshold_days)
    summary = attempt_heal(dry_run=dry_run)
    print(f"[run-all] dry_run={dry_run}: {json.dumps(summary, indent=2)}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Self-healing scraper CLI (see AGENTS.md Licao #15).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_all = sub.add_parser("run-all", help="Audit + reactivate every disabled scraper")
    p_all.add_argument("--dry-run", action="store_true")
    p_all.add_argument("--threshold-days", type=int, default=None)

    p_test = sub.add_parser("test-store", help="Heal exactly one scraper")
    p_test.add_argument("name", type=str)
    p_test.add_argument("--dry-run", action="store_true")

    sub.add_parser("list-disabled", help="List all disabled scrapers")

    p_fail = sub.add_parser("failures", help="Show recent scraper_health_log events for a scraper")
    p_fail.add_argument("name", type=str)
    p_fail.add_argument("--days", type=int, default=30)

    args = parser.parse_args()

    try:
        if args.cmd == "run-all":
            summary = run_all(dry_run=args.dry_run, threshold_days=args.threshold_days)
            rc = 0 if summary.get("error") is None else 1
        elif args.cmd == "test-store":
            test_store(args.name, dry_run=args.dry_run)
            rc = 0
        elif args.cmd == "list-disabled":
            list_disabled()
            rc = 0
        elif args.cmd == "failures":
            failures(args.name, days=args.days)
            rc = 0
        else:
            parser.print_help()
            rc = 2
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        rc = 1

    return rc


if __name__ == "__main__":
    sys.exit(main())
