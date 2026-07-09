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
from datetime import UTC, datetime
from pathlib import Path

# Use Path objects for consistency
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.doc_utils import (  # noqa: E402
    pulse_check,
    read_frontmatter,
    write_frontmatter,
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

def _replace_counter_smart(
    text: str,
    new_val: str,
    label_pat: str,
    old_val: str,
) -> tuple[str, bool]:
    """Substitui primeira ocorrência de `old_val + label` por `new_val + label (era old_val)`.

    Guardas:
      1. Se novo == antigo: nada a fazer (retorna False).
      2. Se já existir `(era N)` na linha: não duplica, apenas atualiza o número.
      3. Aplica apenas a primeira ocorrência.
      4. Se `label_pat` começa com `prefix:`, trata como label-prefixado
         (número APÓS o label, não antes). Formato especial: `prefix:Python|python`.
    """
    if not old_val or str(new_val) == str(old_val):
        return text, False

    if label_pat.startswith("prefix:"):
        prefix_src = label_pat[len("prefix:"):]
        prefix_pat = prefix_src.split("|", 1)
        alt = "|".join(re.escape(p) for p in prefix_pat)
        pattern = rf"(?:{alt})\s+{re.escape(str(old_val))}"
        full_match = re.search(pattern, text, flags=re.IGNORECASE)
        if not full_match:
            return text, False
        start, end = full_match.span()
        replacement = f"{prefix_pat[0]} {new_val}"
        new_text = text[:start] + replacement + text[end:]
        return new_text, new_text != text

    pattern = rf"\b{re.escape(str(old_val))}\s+({label_pat})\b"
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return text, False

    start, end = m.span()
    text_after = text[end:end + 80]
    if _has_existing_era_label(text_after):
        replacement = f"{new_val} {m.group(1)}"
    else:
        replacement = f"{new_val} {m.group(1)} (era {old_val})"

    new_text = text[:start] + replacement + text[end:]
    return new_text, new_text != text


def _replace_counter_any(
    text: str,
    new_val: str,
    label_pat: str,
) -> tuple[str, bool]:
    """Find first occurrence of ANY number + label in body and replace with new_val.

    Fallback for when _replace_counter_smart can't find old_val+label in body
    (e.g., body has a different stale value that was never in frontmatter).

    If number already matches new_val, returns (text, False) — no change.
    If different number found, replaces with ``new_val label (era <found_val>)``,
    respecting existing (era N) suffixes to avoid double-marking.
    If no match at all, returns (text, False).
    """
    if label_pat.startswith("prefix:"):
        prefix_src = label_pat[len("prefix:"):]
        prefix_pat = prefix_src.split("|", 1)
        alt = "|".join(re.escape(p) for p in prefix_pat)
        pattern = rf"(?:{alt})\s+(\d+(?:\.\d+)*)"
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            return text, False
        found_val = m.group(1)
        if found_val == str(new_val):
            return text, False
        start, end = m.span()
        if _has_existing_era_label(text[end:end + 80]):
            replacement = f"{prefix_pat[0]} {new_val}"
        else:
            replacement = f"{prefix_pat[0]} {new_val} (era {found_val})"
        new_text = text[:start] + replacement + text[end:]
        return new_text, True

    pattern = rf"\b(\d+)\s+({label_pat})\b"
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return text, False
    found_val = m.group(1)
    if found_val == str(new_val):
        return text, False
    label = m.group(2)
    start, end = m.span()
    if _has_existing_era_label(text[end:end + 80]):
        replacement = f"{new_val} {label}"
    else:
        replacement = f"{new_val} {label} (era {found_val})"
    new_text = text[:start] + replacement + text[end:]
    return new_text, True


def _has_existing_era_label(text_after: str) -> bool:
    """Detecta '(era N)' imediatamente após a posição atual."""
    return bool(re.match(r"\s+\(era\s+[0-9.]+\)", text_after))


def _bump_semver_like(cur: str) -> str:
    try:
        parts = cur.split(".")
        if len(parts) == 3:
            return f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
        return "0.0.2"
    except Exception:
        return "0.0.2"


def apply_intelligent(path: Path, truth: dict, dry_run: bool = True):
    """Intelligent merge of truth into doc.

    Múltiplas chaves (tests_total, pages_count, python_version). Guardas:
      - Dedup `(era N)`: não duplica sufixo já existente
      - Idempotente: se novo == truth_at[key], não toca
      - Bumps current_version após mudança real

    Retorna True se houve mudança (em dry-run = "would change").
    """
    fm, body = read_frontmatter(path)
    if not fm:
        print(f"  [SKIP] {path.name}: no frontmatter to anchor changes")
        return False

    truth_at = dict(fm.get("truth_at") or {})
    test_counts: dict = truth.get("test_counts", {}) or {}
    real_total = int(test_counts.get("unit", 0)) + int(test_counts.get("schema", 0))
    real_pages = int(truth.get("pages_count", 0))
    page_truth = truth.get("page_truth") or {}
    real_python = str(page_truth.get("python_version", "3.14.6"))

    counter_plan: list[tuple[str, str, str, str]] = [
        (
            "tests_total",
            str(real_total),
            r"(tests?|testes|passing|total)",
            str(truth_at.get("tests_total", "")),
        ),
        (
            "pages_count",
            str(real_pages),
            r"(páginas?|pages?|telas?|módulos?|abas?)",
            str(truth_at.get("pages_count", "")),
        ),
        (
            "python_version",
            real_python,
            "prefix:Python|python",
            str(truth_at.get("python_version", "")),
        ),
    ]
    counter_plan = [c for c in counter_plan if c[3]]

    new_body = body
    changed_body = False
    body_changes_summary: list[str] = []
    for key, new_val, label_pat, old_val in counter_plan:
        new_body, ch = _replace_counter_smart(new_body, new_val, label_pat, old_val)
        if not ch:
            # Fallback: old_val not found in body (e.g., body has different stale value).
            # Try direct body scan for ANY number+label mismatch.
            new_body, ch = _replace_counter_any(new_body, new_val, label_pat)
        if ch:
            changed_body = True
            body_changes_summary.append(f"{key}: {old_val} -> {new_val}")

    new_truth_at = dict(truth_at)
    changed_fm = False
    if truth_at.get("tests_total") != real_total:
        new_truth_at["tests_total"] = real_total
        changed_fm = True
    if truth_at.get("pages_count") != real_pages:
        new_truth_at["pages_count"] = real_pages
        changed_fm = True
    if truth_at.get("python_version") != real_python:
        new_truth_at["python_version"] = real_python
        changed_fm = True

    any_changed = changed_fm or changed_body
    if not any_changed:
        return False

    cur_version = str(fm.get("current_version", "0.0.0"))
    if cur_version == "0.0.0":
        new_version = "0.0.1"
    elif changed_fm:
        new_version = _bump_semver_like(cur_version)
    else:
        new_version = cur_version
    fm["truth_at"] = new_truth_at
    fm["current_version"] = new_version

    if dry_run:
        print(f"  [DRY-RUN] {path.name} would change:")
        for s in body_changes_summary:
            print(f"               body: {s}")
        print(f"               current_version: {cur_version} -> {new_version}")
        return True

    write_frontmatter(path, fm, new_body)
    print(f"  [OK] {path.name} updated:")
    for s in body_changes_summary:
        print(f"               body: {s}")
    print(f"               current_version: {cur_version} -> {new_version}")
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
