#!/usr/bin/env python3
"""
Check store drift between YAML and DB.
Reports: MISSING in DB, ORPHAN in DB, FIELD DRIFT.
"""

import sys
import yaml
import json
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.supabase_client import get_service_client


YAML_PATH = Path("config/stores.yaml")
DEDUP_THRESHOLD = 92


def load_yaml_stores() -> dict[str, dict]:
    """Load stores from YAML, keyed by name."""
    with open("config/stores.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {s["name"]: s for s in data.get("stores", [])}


def load_db_stores() -> dict[str, dict]:
    """Load stores from DB, keyed by name."""
    client = get_service_client()
    res = client.table("stores").select("*").execute()
    return {s["name"]: s for s in (res.data or [])}


def normalize(val: Any) -> str:
    """Normalize value for comparison."""
    if val is None:
        return ""
    if isinstance(val, bool):
        return str(val).lower()
    if isinstance(val, (list, dict)):
        return str(sorted(val)) if isinstance(val, list) else str(sorted(val.items()))
    return str(val).strip()


def compare_stores(yaml_store: dict, db_store: dict, fields: list[str]) -> dict:
    """Compare YAML vs DB store. Returns dict of differences."""
    diff = {}
    for field in ["tier", "type", "logistics", "city", "zone", "coverage",
                  "collection_method", "contact", "source", "priority",
                  "scraper", "base_url", "api_endpoint", "search_url",
                  "url_pattern", "publish_day", "visit_frequency",
                  "contact", "selectors", "api_endpoint", "base_url",
                  "search_url", "url_pattern", "config"]:
        y_val = yaml_store.get(field)
        d_val = db_store.get(field)
        if normalize(y_val) != normalize(d_val):
            diff[field] = {"yaml": y_val, "db": d_val}
    return diff


def check_drift(dry_run: bool = False, threshold: int = 92) -> dict:
    """Check drift between YAML and DB. Returns report dict."""
    yaml_stores = load_yaml_stores()
    db_stores = load_db_stores()

    report: dict = {
        "missing_in_db": [],      # in YAML but not in DB
        "orphan_in_db": [],       # in DB but not in YAML
        "field_drift": [],        # field differences
        "similar_names": [],      # potential duplicates (RapidFuzz >= threshold)
    }

    # Check for missing/removed
    for name, y_store in yaml_stores.items():
        if name not in db_stores:
            report["missing_in_db"].append({"name": name, "yaml": y_store})
        else:
            # Compare fields
            diff = compare_stores(y_store, db_stores[name], [])
            if diff:
                report["field_drift"].append({"name": name, "diff": diff})

    # Orphans in DB
    for name, d_store in db_stores.items():
        if name not in yaml_stores:
            report["orphan_in_db"].append({"name": name, "db": d_store})

    # Find similar names (potential duplicates)
    from rapidfuzz import fuzz
    all_names = list(yaml_stores.keys()) + [n for n in db_stores if n not in yaml_stores]
    for i, n1 in enumerate(all_names):
        for n2 in all_names[i+1:]:
            score = fuzz.token_set_ratio(n1, n2)
            if score >= threshold:
                report["similar_names"].append({
                    "name1": n1, "name2": n2, "similarity": score / 100.0
                })

    return report


def print_report(report: dict, format: str = "text"):
    """Print drift report."""
    if format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    print("=" * 60)
    print("STORE DRIFT REPORT")
    print("=" * 60)

    if report["missing_in_db"]:
        print(f"\n[X] MISSING IN DB ({len(report['missing_in_db'])}):")
        for item in report["missing_in_db"]:
            print(f"  - {item['name']}")

    if report["orphan_in_db"]:
        print(f"\n[G] ORPHAN IN DB ({len(report['orphan_in_db'])}):")
        for item in report["orphan_in_db"]:
            print(f"  - {item['name']} (tier={item['db'].get('tier')}, active={item['db'].get('is_active')})")

    if report["field_drift"]:
        print(f"\n[!] FIELD DRIFT ({len(report['field_drift'])}):")
        for item in report["field_drift"]:
            print(f"  {item['name']}:")
            for field, vals in item["diff"].items():
                print(f"    {field}: YAML={item['diff'][field]['yaml']!r} vs DB={item['diff'][field]['db']!r}")

    if report["similar_names"]:
        print(f"\n[S] SIMILAR NAMES ({len(report['similar_names'])}):")
        for item in report["similar_names"]:
            print(f"  {item['name1']} <-> {item['name2']} ({item['similarity']:.0%})")

    total_issues = (len(report["missing_in_db"]) +
                    len(report["orphan_in_db"]) +
                    len(report["field_drift"]))
    print(f"\n{'='*60}")
    print(f"TOTAL ISSUES: {total_issues}")
    print(f"{'='*60}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check store drift YAML <-> DB")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--threshold", type=int, default=92, help="Similarity threshold")
    args = parser.parse_args()

    report = check_drift(threshold=args.threshold)
    print_report(report, "json" if args.json else "text")

    # Exit code: 0 = no issues, 1 = drift found
    has_issues = any([report["missing_in_db"], report["orphan_in_db"], report["field_drift"]])
    sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()