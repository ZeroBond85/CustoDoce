"""
Sync MD v2 — Intelligent incremental synchronization for project documentation.
Complementary to sync_docs.py, focusing on Raio-X and other snapshot-based docs.

Features:
- Frontmatter-based state tracking (version, truth_at).
- Pulse check: read-only health audit vs current truth.
- Snapshots: creates dated release copies in docs/archive/releases/.
- Intelligent apply: merge truth changes without erasing history.
- Injector: one-shot migration to frontmatter regime.
"""

import argparse
import re
import sys
from datetime import datetime, UTC
from pathlib import Path

# Use Path objects for consistency
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.doc_utils import (  # noqa: E402
    read_frontmatter,
    write_frontmatter,
    pulse_check,
)

# To avoid duplicating complex logic, we import the state builder from sync_docs
# If it's an internal function, we access it via the module
try:
    from scripts.sync_docs import _build_agents_state
except ImportError:
    # Fallback if sync_docs is not importable or _build_agents_state is missing
    def _build_agents_state():
        return {"updated_at": "unknown", "test_counts": {}, "total_tests": 0, "pages_count": 0}

# ═══════════════════════════════════════════════════════════════════
# CORE LOGIC
# ═══════════════════════════════════════════════════════════════════

def pulse(targets: list[Path], truth: dict):
    """Health check of docs vs truth. Read-only."""
    print(f"\n--- [Pulse Check] Scanning {len(targets)} files ---")
    findings = []
    for path in targets:
        fm, body = read_frontmatter(path)
        if not fm:
            # File is in legacy mode (no frontmatter)
            rel_path = path.relative_to(_ROOT) if path.is_relative_to(_ROOT) else path.name
            findings.append(f"  [LEGACY] {rel_path}: Missing frontmatter")
            continue

        warnings = pulse_check(fm, truth)
        if warnings:
            rel_path = path.relative_to(_ROOT) if path.is_relative_to(_ROOT) else path.name
            findings.append(f"  [STALE] {rel_path} (v{fm.get('current_version', '?')})")
            for w in warnings:
                findings.append(f"    - {w}")
        else:
            rel_path = path.relative_to(_ROOT) if path.is_relative_to(_ROOT) else path.name
            findings.append(f"  [OK] {rel_path} (v{fm.get('current_version', '?')})")


    print("\n".join(findings))
    return len([f for f in findings if "STALE" in f]) > 0

def snapshot(version: str, targets: list[Path]):
    """Creates immutable release copies in docs/archive/releases/."""
    release_dir = _ROOT / "docs" / "archive" / "releases"
    release_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y-%m-%d")
    changes = []

    for path in targets:
        slug = path.stem.lower().replace(" ", "_")
        dest = release_dir / f"{ts}-v{version}-{slug}.md"

        # Copy content
        content = path.read_text(encoding="utf-8")
        dest.write_text(content, encoding="utf-8")
        changes.append(f"  {path.name} -> {dest.name}")

    print(f"\n--- [Snapshot] Version {version} archived ---")
    print("\n".join(changes))

def apply_intelligent(path: Path, truth: dict, dry_run: bool = True):
    """
    Intelligent merge of truth into doc.
    1. Body merge first (to use old truth for replacements).
    2. Updates frontmatter (truth_at, current_version).
    """
    fm, body = read_frontmatter(path)
    if not fm:
        print(f"  [SKIP] {path.name}: no frontmatter to anchor changes")
        return False

    real_total = sum(truth.get("test_counts", {}).values())
    real_pages = truth.get("pages_count", 0)

    def replace_counter(text, key, new_val, label_pat):
        # Find patterns like "709 tests"
        pattern = rf"\b(\d+)\s*{label_pat}\b"
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if not matches:
            return text, False

        # We only update the first occurrence that matches the OLD truth_at
        old_val = str(fm.get("truth_at", {}).get(key, ""))
        if old_val and old_val != str(new_val):
            new_text = re.sub(
                rf"({re.escape(old_val)})\s*({label_pat})",
                rf"{new_val} \2 (era {old_val})",
                text,
                count=1,
                flags=re.IGNORECASE
            )
            return new_text, new_text != text
        return text, False

    new_body, tests_changed = replace_counter(body, "tests_total", real_total, r"(tests?|passing|total)")
    new_body, pages_changed = replace_counter(new_body, "pages_count", real_pages, r"(páginas?|pages?|módulos?)")

    # Now update frontmatter
    new_truth_at = fm.get("truth_at", {})
    changed = False

    if new_truth_at.get("tests_total") != real_total:
        new_truth_at["tests_total"] = real_total
        changed = True
    if new_truth_at.get("pages_count") != real_pages:
        new_truth_at["pages_count"] = real_pages
        changed = True

    fm["truth_at"] = new_truth_at

    if tests_changed or pages_changed:
        changed = True

    if not changed:
        return False

    if dry_run:
        print(f"  [DRY-RUN] Would update {path.name} (truth diverge)")
        return True

    write_frontmatter(path, fm, new_body)
    return True

def inject_frontmatter(targets: list[Path]):
    """One-shot migration to frontmatter regime."""
    print("\n--- [Injector] Migrating files to frontmatter ---")
    for path in targets:
        fm, body = read_frontmatter(path)
        if fm:
            continue

        # Default frontmatter for Raio-X / Archive
        default_fm = {
            "doc_type": "snapshot",
            "slug": path.stem.lower().replace(" ", "_"),
            "current_version": "0.0.0",
            "truth_at": {
                "tests_total": 0,
                "pages_count": 0,
            }
        }
        write_frontmatter(path, default_fm, body)
        print(f"  Injected into {path.name}")

# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Sync MD v2 — Intelligent Doc Sync")
    parser.add_argument("--pulse", action="store_true", help="Read-only health check")
    parser.add_argument("--snapshot", type=str, help="Version to snapshot (e.g. 0.2.6)")
    parser.add_argument("--apply", action="store_true", help="Apply truth updates to docs")
    parser.add_argument("--inject-frontmatter", action="store_true", help="Migrate files to FM regime")
    parser.add_argument("--targets", type=str, help="Comma separated paths to files (relative to root)")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Preview changes")

    args = parser.parse_args()

    # Default targets: everything in docs/archive/
    if args.targets:
        targets = [ _ROOT / p.strip() for p in args.targets.split(",") ]
    else:
        targets = sorted((_ROOT / "docs" / "archive").glob("*.md"))

    truth = _build_agents_state()

    if args.inject_frontmatter:
        inject_frontmatter(targets)

    if args.pulse:
        pulse(targets, truth)

    if args.snapshot:
        snapshot(args.snapshot, targets)

    if args.apply:
        print("\n--- [Applying Intelligent Sync] ---")
        for path in targets:
            if apply_intelligent(path, truth, dry_run=args.dry_run):
                print(f"  Updated {path.name}")

if __name__ == "__main__":
    main()
