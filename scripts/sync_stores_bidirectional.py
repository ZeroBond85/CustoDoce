#!/usr/bin/env python3
"""
Bidirectional sync stores.yaml <-> DB with dry-run, lock, diff report.
Usage:
  python scripts/sync_stores_bidirectional.py --dry-run
  python scripts/sync_stores_bidirectional.py --apply
  python scripts/sync_stores_bidirectional.py --report
"""

import sys
import json
import yaml
import argparse
import re
import unicodedata
from pathlib import Path
from datetime import UTC, datetime
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.supabase_client import get_service_client
from scripts.check_store_drift import check_drift
from scripts.sync_lock import SyncLock
from scripts.backup_stores_yaml import backup_stores_yaml

YAML_PATH = Path("config/stores.yaml")
DB_FIELDS = [
    "name", "tier", "type", "scraper", "is_active", "city", "base_url",
    "search_url", "api_endpoint", "selectors", "publish_day",
    "url_pattern", "visit_frequency", "logistics", "zone", "coverage",
    "contact", "priority", "config", "scraper", "type", "tier",
    "url_pattern", "base_url", "api_endpoint", "search_url",
    "visit_frequency", "logistics", "zone", "coverage", "contact",
    "priority", "selectors"
]


def slugify(name: str) -> str:
    """Generate deterministic slug from store name for stores.id (TEXT PRIMARY KEY)."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s[:50]


def load_yaml_stores() -> dict[str, dict]:
    with open("config/stores.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {s["name"]: s for s in data.get("stores", [])}


def load_db_stores() -> dict[str, dict]:
    client = get_service_client()
    res = client.table("stores").select("*").execute()
    return {s["name"]: s for s in (res.data or [])}


def normalize(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, bool):
        return str(val).lower()
    if isinstance(val, (list, dict)):
        return json.dumps(val, sort_keys=True)
    return str(val).strip()


def compare(yaml_val: Any, db_val: Any) -> bool:
    """Compare YAML value with DB value (normalized)."""
    return normalize(yaml_val) == normalize(db_val)


def generate_diff(yaml_store: dict, db_store: dict) -> dict:
    """Return dict of field differences."""
    diff = {}
    for field in ["tier", "type", "scraper", "is_active", "city", "base_url",
                  "search_url", "api_endpoint", "selectors", "publish_day",
                  "url_pattern", "visit_frequency", "logistics", "zone",
                  "coverage", "contact", "source", "priority", "config",
                  "url_pattern", "base_url", "api_endpoint", "search_url",
                  "visit_frequency", "logistics", "zone", "coverage",
                  "contact", "priority", "selectors", "config"]:
        y_val = yaml_store.get(field)
        d_val = db_store.get(field)
        if not compare(y_val, d_val):
            diff[field] = {"yaml": yaml_store.get(field), "db": db_store.get(field)}
    return diff


def dry_run() -> dict:
    """Dry run sync - shows what would change without applying."""
    client = get_service_client()
    yaml_stores = load_yaml_stores()
    db_stores = load_db_stores()

    report = {
        "missing_in_db": [],      # in YAML not in DB
        "orphan_in_db": [],       # in DB not in YAML
        "field_changes": [],      # field differences
        "would_create": [],
        "would_update": [],
        "would_delete": [],
    }

    # Check YAML stores
    for name, y_store in yaml_stores.items():
        if name not in db_stores:
            report["would_create"].append({"name": name, "data": y_store})
        else:
            diff = generate_diff(y_store, db_stores[name])
            if diff:
                report["field_changes"].append({"name": name, "diff": diff})

    # Orphan in DB
    for name, db_store in db_stores.items():
        if name not in yaml_stores:
            report["orphan_in_db"].append({"name": name, "db": db_store})

    return report


def apply_sync(dry_run: bool = False) -> dict:
    """Apply sync changes. If dry_run, only report."""
    client = get_service_client()
    yaml_stores = load_yaml_stores()
    db_stores = load_db_stores()

    results = {"created": 0, "updated": 0, "skipped": 0, "errors": []}

    # Upsert YAML stores
    for name, y_store in yaml_stores.items():
        store_id = y_store.get("id") or slugify(name)
        data = {
            "id": store_id,
            "name": name,
            "tier": y_store.get("tier", 3),
            "type": y_store.get("type", "manual"),
            "scraper": y_store.get("scraper"),
            "is_active": y_store.get("is_active", True),
            "city": y_store.get("city", ""),
            "base_url": y_store.get("base_url", ""),
            "search_url": y_store.get("search_url", ""),
            "api_endpoint": y_store.get("api_endpoint", ""),
            "selectors": y_store.get("selectors", {}),
            "publish_day": y_store.get("publish_day", ""),
            "url_pattern": y_store.get("url_pattern", ""),
            "visit_frequency": y_store.get("visit_frequency", ""),
            "logistics": y_store.get("logistics", "pickup_local"),
            "zone": y_store.get("zone", ""),
            "coverage": y_store.get("coverage", ""),
            "contact": y_store.get("contact", ""),
            "source": y_store.get("source", "yaml"),
            "priority": y_store.get("priority", 99),
            "config": y_store.get("config", {}),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        if name in load_db_stores():
            if not dry_run:
                try:
                    client.table("stores").update(data).eq("name", name).execute()
                    print(f"  [UPDATE] {name}")
                except Exception as e:
                    print(f"  [ERROR] {name}: {e}")
                    continue
            results["updated"] += 1
        else:
            if not dry_run:
                try:
                    client.table("stores").insert(data).execute()
                    print(f"  [CREATE] {name}")
                except Exception as e:
                    print(f"  [ERROR] {name}: {e}")
                    continue
            results["created"] += 1

    return {"results": results, "dry_run": dry_run}


def generate_report(report: dict, format: str = "markdown") -> str:
    """Generate markdown or JSON report."""
    if format == "json":
        return json.dumps(report, indent=2, ensure_ascii=False)

    lines = [
        "# Store Sync Report",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "## Summary",
        f"- To Create: {len(report.get('would_create', []))}",
        f"- To Update: {len(report.get('field_changes', []))}",
        f"- Orphans in DB: {len(report.get('orphan_in_db', []))}",
        "",
        "## Details",
    ]

    if report.get("would_create"):
        lines.append("### To Create")
        for item in report["would_create"]:
            lines.append(f"- **{item['name']}**")

    if report.get("field_changes"):
        lines.append("### Field Changes")
        for item in report["field_changes"]:
            lines.append(f"### {item['name']}")
            for field, vals in item.get("diff", {}).items():
                lines.append(f"  - **{field}**: `{vals['yaml']!r}` → `{vals['db']!r}`")

    if report.get("orphan_in_db"):
        lines.append("### Orphans in DB (not in YAML)")
        for item in report["orphan_in_db"]:
            lines.append(f"- {item['name']} (tier={item['db'].get('tier')}, active={item['db'].get('is_active')})")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Bidirectional sync stores.yaml <-> DB")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without applying")
    parser.add_argument("--apply", action="store_true", help="Apply changes (requires --apply)")
    parser.add_argument("--report", action="store_true", help="Generate drift report")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--force", action="store_true", help="Force without lock")
    args = parser.parse_args()

    if args.report:
        report = check_drift()
        print(generate_report(report, "json" if args.json else "markdown"))
        return

    if not args.dry_run and not args.apply:
        print("Error: specify --dry-run or --apply")
        sys.exit(1)

    # Acquire lock
    lock = SyncLock()
    if not args.force:
        if not lock.acquire():
            print("Could not acquire lock (another sync running?)")
            sys.exit(1)
        print("[LOCK] Acquired")

    try:
        # Backup before sync
        if args.apply:
            backup_stores_yaml()
            print("[OK] Backup created")

        if args.dry_run:
            report = dry_run()
            print(generate_report(report, "json" if args.json else "markdown"))
        elif args.apply:
            result = apply_sync(dry_run=False)
            print(json.dumps(result, indent=2))
    finally:
        if not args.force:
            lock.release()


if __name__ == "__main__":
    main()