"""CLI entry point for sync_docs_v2.

Usage:
    python -m scripts.sync_docs_v2 --analyze       # classify stale refs
    python -m scripts.sync_docs_v2 --sync           # auto-update CURRENT blocks
    python -m scripts.sync_docs_v2 --sync --dry-run  # preview changes
    python -m scripts.sync_docs_v2 --dump-truth     # print truth JSON
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from scripts.sync_docs_v2.classifier import classify
from scripts.sync_docs_v2.parser import scan_all_md
from scripts.sync_docs_v2.truth import build_truth
from scripts.sync_docs_v2.updater import sync_file

_ROOT = Path(__file__).resolve().parent.parent.parent


def run_analyze() -> list[dict]:
    """Run scanner + classifier on all .md files."""
    raw = scan_all_md()
    for f in raw:
        f["classification"] = classify(f["heading"], f["match"], f["file"])
    return raw


def run_sync(dry_run: bool = False) -> tuple[list[str], list[dict]]:
    """Sync all CURRENT blocks with truth values.

    Returns (changes, findings).
    """
    findings = run_analyze()
    truth = build_truth()
    all_changes: list[str] = []

    # Group findings by file
    by_file: dict[str, list[dict]] = {}
    for f in findings:
        by_file.setdefault(f["file"], []).append(f)

    for file_rel, file_findings in by_file.items():
        fpath = _ROOT / file_rel
        changes = sync_file(fpath, file_findings, truth, dry_run=dry_run)
        all_changes.extend(changes)

    return all_changes, findings


def _print_findings(findings: list[dict]):
    from collections import Counter

    counts = Counter(f["classification"] for f in findings)
    print(
        f"Total: {len(findings)}  CURRENT: {counts.get('CURRENT', 0)}  "
        f"HISTORICAL: {counts.get('HISTORICAL', 0)}  "
        f"AMBIGUOUS: {counts.get('AMBIGUOUS', 0)}"
    )
    print()

    if not findings:
        return

    for f in findings:
        cl = f["classification"]
        sep = "  "
        print(f"  [{cl:<10}] {f['file']}:{f['line']}")
        print(f"{sep}heading: {f['heading'][:100]}")
        print(f"{sep}match:   '{f['match']}'")
        print()


def _ensure_utf8():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        with contextlib.suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8()
    parser = argparse.ArgumentParser(description="sync_docs v2 — heading-aware stale ref management")
    parser.add_argument("--analyze", action="store_true", help="Classify stale refs in all .md")
    parser.add_argument("--sync", action="store_true", help="Auto-update CURRENT blocks with truth values")
    parser.add_argument("--dry-run", action="store_true", help="Preview --sync changes without applying")
    parser.add_argument("--dump-truth", action="store_true", help="Print truth JSON and exit")
    args = parser.parse_args(argv)

    if args.dump_truth:
        truth = build_truth()
        print(json.dumps(truth, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.analyze:
        findings = run_analyze()
        _print_findings(findings)
        ambiguous = sum(1 for f in findings if f["classification"] == "AMBIGUOUS")
        if ambiguous > 0:
            print(f"\n[BLOCK] {ambiguous} AMBIGUOUS ref(s) found — CI blocked")
            return 1
        return 0

    if args.sync:
        changes, findings = run_sync(dry_run=args.dry_run)
        if changes:
            print(f"Changes to apply ({'dry-run' if args.dry_run else 'live'}):")
            for c in changes:
                print(c)
            print()
            print(f"Total: {len(changes)} changes across {len(findings)} findings")
        else:
            print("No stale CURRENT refs found. All docs are in sync.")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
